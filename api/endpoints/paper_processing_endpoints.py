from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Response, status, Depends
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from typing import Union, List, Optional, Dict, Any
from pydantic import BaseModel
from sqlalchemy.orm import Session
from api.types.paper_processing_api_models import Paper, JobStatusResponse, MinimalPaperItem
from paperprocessor.client import process_paper_pdf
from shared.db import get_session
from api.models import PaperRow, RequestedPaperRow, PaperSlugRow, NewPaperNotification
from shared.arxiv.client import normalize_id, parse_url, fetch_metadata, head_pdf, download_pdf
from shared.arxiv.models import ArxivMetadata
import os
import uuid
from datetime import datetime
from uuid import UUID
from api.background_jobs import create_job, get_job_status, update_job_status
import logging
import re
import hashlib
import json as _json

router = APIRouter()
logger = logging.getLogger(__name__)

# --- Simple HTTP Basic admin protection ---
security = HTTPBasic()

def require_admin(credentials: HTTPBasicCredentials = Depends(security)):
    import os, secrets
    expected_user = "admin"
    expected_pass = os.environ.get("ADMIN_BASIC_PASSWORD", "")
    ok_user = secrets.compare_digest(credentials.username, expected_user)
    ok_pass = secrets.compare_digest(credentials.password, expected_pass)
    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": 'Basic realm="Management"'},
        )
    return True

async def process_paper_in_background(job_id: str, contents: bytes):
    """
    A wrapper function to run the PDF processing in the background
    and update the job status upon completion or failure.
    """
    try:
        result = await process_paper_pdf(contents)
        update_job_status(job_id, "completed", result)
        logger.info(f"Job {job_id} completed successfully.")
    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}", exc_info=True)
        update_job_status(job_id, "failed", str(e))

@router.post("/papers/process", status_code=status.HTTP_202_ACCEPTED, response_model=JobStatusResponse)
async def process_paper(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """
    Accepts a PDF file, starts a background processing job, and returns a job ID.
    """
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Invalid file type. Only PDFs are accepted.")

    contents = await file.read()
    job_id = create_job()
    
    background_tasks.add_task(process_paper_in_background, job_id, contents)
    
    return {"job_id": job_id, "status": "processing"}

@router.get("/papers/process/{job_id}", response_model=Union[Paper, JobStatusResponse])
async def get_paper_status(job_id: str, response: Response):
    """
    Polls for the status of a paper processing job.
    - Returns a 202 status code while the job is processing.
    - Returns the final JSON result with a 200 status code upon completion.
    - Returns an error if the job failed.
    """
    job = get_job_status(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    if job["status"] == "processing":
        response.status_code = status.HTTP_202_ACCEPTED
        return {"job_id": job_id, "status": "processing"}
    
    if job["status"] == "failed":
        raise HTTPException(status_code=500, detail=job.get("result", "An unknown error occurred."))

    # If completed, Pydantic will automatically validate and return the Paper model
    return job["result"] 


class EnqueueArxivRequest(BaseModel):
    url: str


class EnqueueArxivResponse(BaseModel):
    job_db_id: int
    paper_uuid: str
    status: str


@router.post("/papers/enqueue_arxiv", response_model=EnqueueArxivResponse)
async def enqueue_arxiv(req: EnqueueArxivRequest, db: Session = Depends(get_session)):
    try:
        norm = await normalize_id(req.url)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid arXiv URL or identifier")

    paper_uuid = str(uuid.uuid4())

    # Duplicate check
    existing = db.query(PaperRow).filter(PaperRow.arxiv_id == norm.arxiv_id).first()
    if existing:
        raise HTTPException(status_code=409, detail="A paper with this arXiv ID already exists")

    job = PaperRow(
        paper_uuid=paper_uuid,
        arxiv_id=norm.arxiv_id,
        arxiv_version=norm.version,
        arxiv_url=req.url,
        status="not_started",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    return EnqueueArxivResponse(job_db_id=job.id, paper_uuid=paper_uuid, status=job.status)


class JobDbStatus(BaseModel):
    paper_uuid: str
    status: str
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    arxiv_id: str
    arxiv_version: str | None = None
    arxiv_url: str | None = None
    title: str | None = None
    authors: str | None = None
    num_pages: int | None = None
    thumbnail_data_url: str | None = None
    processing_time_seconds: float | None = None
    total_cost: float | None = None
    avg_cost_per_page: float | None = None


 
@router.get("/papers/minimal", response_model=List[MinimalPaperItem])
def list_minimal_papers(db: Session = Depends(get_session)):
    """
    Returns a minimal list of papers: paper_uuid, title, authors, thumbnail_data_url, slug.
    Caches scanning of JSON files across requests by fingerprinting the directory contents.
    Slug mappings are refreshed from DB each call to reflect latest state.
    """
    base_dir = _paperjsons_dir()
    logger.info("GET /papers/minimal base_dir=%s", base_dir)
    fp = _build_dir_fingerprint(base_dir)
    if not fp:
        logger.warning("Minimal list fingerprint empty; directory may be missing or empty: %s", base_dir)
        items: List[MinimalPaperItem] = []
    else:
        items = _get_minimal_items_for_fingerprint(fp, base_dir)
    logger.info("Minimal list items_scanned=%d", len(items))

    # Refresh slug mapping from DB (latest non-tombstone per paper_uuid)
    slug_rows = (
        db.query(PaperSlugRow)
        .filter(PaperSlugRow.tombstone == False)  # noqa: E712
        .all()
    )
    latest_by_uuid: Dict[str, Dict[str, Any]] = {}
    for r in slug_rows:
        puid = r.paper_uuid
        if not puid:
            continue
        current = latest_by_uuid.get(puid)
        if current is None or (r.created_at and current.get("created_at") and r.created_at > current["created_at"]):
            latest_by_uuid[puid] = {"slug": r.slug, "created_at": r.created_at}

    # Merge slugs into items
    for it in items:
        m = latest_by_uuid.get(it.paper_uuid)
        it.slug = m["slug"] if m else None
    merged_slugs = sum(1 for it in items if it.slug)
    logger.info("Minimal list merged_slugs=%d", merged_slugs)
    return items



@router.get("/papers/{paper_uuid}", response_model=JobDbStatus)
def get_paper_by_uuid(paper_uuid: UUID, db: Session = Depends(get_session)):
    logger.info("GET /papers/%s", paper_uuid)
    job = db.query(PaperRow).filter(PaperRow.paper_uuid == str(paper_uuid)).first()
    if not job:
        logger.warning("Paper not found for paper_uuid=%s", paper_uuid)
        raise HTTPException(status_code=404, detail="Job not found")
    logger.info("Found paper paper_uuid=%s status=%s arxiv_id=%s", job.paper_uuid, job.status, job.arxiv_id)
    return JobDbStatus(
        paper_uuid=job.paper_uuid,
        status=job.status,
        error_message=job.error_message,
        created_at=job.created_at,
        updated_at=job.updated_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        arxiv_id=job.arxiv_id,
        arxiv_version=job.arxiv_version,
        arxiv_url=job.arxiv_url,
        title=job.title,
        authors=job.authors,
        num_pages=job.num_pages,
        thumbnail_data_url=getattr(job, 'thumbnail_data_url', None),
        processing_time_seconds=job.processing_time_seconds,
        total_cost=job.total_cost,
        avg_cost_per_page=job.avg_cost_per_page,
    )


@router.get("/papers", response_model=List[JobDbStatus])
def list_papers(status: Optional[str] = None, limit: int = 500, db: Session = Depends(get_session), _admin: bool = Depends(require_admin)):
    q = db.query(PaperRow)
    if status:
        statuses = [s.strip() for s in status.split(",") if s.strip()]
        if statuses:
            q = q.filter(PaperRow.status.in_(statuses))
    q = q.order_by(PaperRow.created_at.desc()).limit(max(1, min(limit, 1000)))
    rows = q.all()
    return [
        JobDbStatus(
            paper_uuid=r.paper_uuid,
            status=r.status,
            error_message=r.error_message,
            created_at=r.created_at,
            updated_at=r.updated_at,
            started_at=r.started_at,
            finished_at=r.finished_at,
            arxiv_id=r.arxiv_id,
            arxiv_version=r.arxiv_version,
            arxiv_url=r.arxiv_url,
            title=r.title,
            authors=r.authors,
            num_pages=r.num_pages,
            thumbnail_data_url=getattr(r, 'thumbnail_data_url', None),
            processing_time_seconds=r.processing_time_seconds,
            total_cost=r.total_cost,
            avg_cost_per_page=r.avg_cost_per_page,
        )
        for r in rows
    ]


class RestartPaperRequest(BaseModel):
    reason: Optional[str] = None


@router.post("/papers/{paper_uuid}/restart", status_code=200)
def restart_paper(paper_uuid: UUID, _body: RestartPaperRequest | None = None, db: Session = Depends(get_session), _admin: bool = Depends(require_admin)):
    row = db.query(PaperRow).filter(PaperRow.paper_uuid == str(paper_uuid)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Paper not found")
    if row.status == "processing":
        raise HTTPException(status_code=409, detail="Paper is already processing")
    # Reset for reprocessing
    row.status = "not_started"
    row.error_message = None
    row.started_at = None
    row.finished_at = None
    row.updated_at = datetime.utcnow()
    db.add(row)
    db.commit()
    return {"paper_uuid": paper_uuid, "status": row.status}


@router.delete("/papers/{paper_uuid}", status_code=200)
def delete_paper(paper_uuid: UUID, db: Session = Depends(get_session), _admin: bool = Depends(require_admin)):
    row = db.query(PaperRow).filter(PaperRow.paper_uuid == str(paper_uuid)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Paper not found")
    # Delete JSON file if exists
    base_dir = os.path.abspath(os.path.join(os.getcwd(), 'data', 'paperjsons'))
    json_path = os.path.join(base_dir, f"{paper_uuid}.json")
    try:
        if os.path.exists(json_path):
            os.remove(json_path)
    except Exception:
        pass
    # Remove DB row
    db.delete(row)
    db.flush()

    # Leave slug tombstones: keep slug entries but null out paper_uuid and mark tombstone
    try:
        slug_rows = db.query(PaperSlugRow).filter(PaperSlugRow.paper_uuid == paper_uuid).all()
        now = datetime.utcnow()
        for s in slug_rows:
            s.paper_uuid = None
            s.tombstone = True
            s.deleted_at = now
            db.add(s)
    except Exception:
        logger.exception("Failed to tombstone slugs for paper_uuid=%s", paper_uuid)

    db.commit()
    return {"deleted": paper_uuid}


# --- Paper existence check ---

class CheckArxivResponse(BaseModel):
    exists: bool
    viewer_url: Optional[str] = None


@router.get("/papers/check_arxiv/{arxiv_id_or_url}", response_model=CheckArxivResponse)
async def check_arxiv(arxiv_id_or_url: str, db: Session = Depends(get_session)):
    """
    Checks if an arXiv paper has been processed and is available, without side-effects.
    Returns the viewer URL if it exists.
    """
    try:
        norm = await normalize_id(arxiv_id_or_url)
        arxiv_id = norm.arxiv_id
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid arXiv URL or identifier")

    job = db.query(PaperRow).filter(PaperRow.arxiv_id == arxiv_id).first()
    if job and job.status == "completed":
        # Check for JSON file existence as a proxy for being fully processed and available.
        base_dir = os.path.abspath(os.path.join(os.getcwd(), 'data', 'paperjsons'))
        json_path = os.path.join(base_dir, f"{job.paper_uuid}.json")
        if os.path.exists(json_path):
            # Resolve the latest, non-tombstoned slug for this paper.
            slug_row = (
                db.query(PaperSlugRow)
                .filter(PaperSlugRow.paper_uuid == job.paper_uuid)
                .filter(PaperSlugRow.tombstone == False)  # noqa: E712
                .order_by(PaperSlugRow.created_at.desc())
                .first()
            )
            if slug_row:
                return CheckArxivResponse(exists=True, viewer_url=f"/paper/{slug_row.slug}")

    return CheckArxivResponse(exists=False, viewer_url=None)


@router.get("/arxiv-metadata/{arxiv_id_or_url}", response_model=ArxivMetadata)
async def get_arxiv_metadata(arxiv_id_or_url: str):
    """
    Fetches paper metadata directly from the arXiv API.
    """
    try:
        norm = await normalize_id(arxiv_id_or_url)
        arxiv_id = norm.arxiv_id
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid arXiv URL or identifier")

    try:
        metadata = await fetch_metadata(arxiv_id)
        return metadata
    except ValueError as e:
        # fetch_metadata raises ValueError if no entry is found
        raise HTTPException(status_code=404, detail=f"Metadata not found for {arxiv_id}: {e}")
    except Exception as e:
        logger.error(f"Failed to fetch metadata for {arxiv_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch metadata from arXiv API")


# --- Request Paper (strict arXiv URL) ---

class RequestArxivRequest(BaseModel):
    url: str
    notification_email: Optional[str] = None


class RequestArxivResponse(BaseModel):
    state: str  # "exists" | "requested"
    viewer_url: Optional[str] = None


@router.post("/papers/request_arxiv", response_model=RequestArxivResponse)
async def request_arxiv(req: RequestArxivRequest, db: Session = Depends(get_session)):
    # Strict URLs only
    raw = (req.url or "").strip()
    if not (raw.startswith("http://") or raw.startswith("https://")):
        raise HTTPException(status_code=400, detail="Only arXiv abs/pdf URLs are accepted")
    try:
        parsed = await parse_url(raw)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid arXiv URL")
    if parsed.url_type not in ("abs", "pdf"):
        raise HTTPException(status_code=400, detail="Only arXiv abs/pdf URLs are accepted")

    # Treat versions as the same paper
    arxiv_id = parsed.arxiv_id
    abs_url = f"https://arxiv.org/abs/{arxiv_id}"
    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

    # If the paper exists and is completed with JSON available, return pretty URL (/paper/<slug>) and DO NOT add to requests
    job = db.query(PaperRow).filter(PaperRow.arxiv_id == arxiv_id).first()
    if job and job.status == "completed":
        base_dir = os.path.abspath(os.path.join(os.getcwd(), 'data', 'paperjsons'))
        json_path = os.path.join(base_dir, f"{job.paper_uuid}.json")
        if os.path.exists(json_path):
            # Resolve or create slug for this paper
            slug_row = (
                db.query(PaperSlugRow)
                .filter(PaperSlugRow.paper_uuid == job.paper_uuid)
                .filter(PaperSlugRow.tombstone == False)  # noqa: E712
                .order_by(PaperSlugRow.created_at.desc())
                .first()
            )
            if not slug_row:
                # Create slug; strict rules: require title and authors; on collision raise
                slug_val = _build_slug_from_title_and_authors(job.title, job.authors)
                exists = db.query(PaperSlugRow).filter(PaperSlugRow.slug == slug_val).first()
                if exists:
                    raise HTTPException(status_code=409, detail="Slug already exists")
                slug_row = PaperSlugRow(slug=slug_val, paper_uuid=job.paper_uuid, tombstone=False, created_at=datetime.utcnow())
                db.add(slug_row)
                db.commit()
                db.refresh(slug_row)
            return RequestArxivResponse(state="exists", viewer_url=f"/paper/{slug_row.slug}")

    # If an email was provided, save it for notification.
    if req.notification_email:
        # Basic email validation, just an @ check
        if "@" not in req.notification_email:
            raise HTTPException(status_code=400, detail="Invalid email address format")

        existing_notification = (
            db.query(NewPaperNotification)
            .filter(NewPaperNotification.arxiv_id == arxiv_id)
            .filter(NewPaperNotification.email == req.notification_email)
            .first()
        )
        if not existing_notification:
            notification_entry = NewPaperNotification(
                email=req.notification_email,
                arxiv_id=arxiv_id,
            )
            db.add(notification_entry)

    # Otherwise, upsert into requested_papers (increment count, update timestamps)
    now = datetime.utcnow()
    existing_req = db.query(RequestedPaperRow).filter(RequestedPaperRow.arxiv_id == arxiv_id).first()
    # Fetch metadata: title/authors; head PDF for page count estimate if possible
    title_val = None
    authors_str = None
    num_pages_val = None
    try:
        meta = await fetch_metadata(arxiv_id)
        title_val = meta.title or None
        authors_str = ", ".join([a.name for a in (meta.authors or [])]) or None
    except Exception:
        logger.exception("Failed to fetch arXiv metadata for %s", arxiv_id)
    try:
        # Download PDF and count pages using PyMuPDF
        pdf = await download_pdf(arxiv_id)
        try:
            import fitz  # PyMuPDF
            with fitz.open(stream=pdf.pdf_bytes, filetype="pdf") as doc:
                num_pages_val = doc.page_count
        except Exception:
            logger.exception("Failed to count pages for %s via PyMuPDF", arxiv_id)
            num_pages_val = None
    except Exception:
        logger.exception("Failed to download PDF to count pages for %s", arxiv_id)

    if existing_req:
        existing_req.request_count = int(existing_req.request_count or 0) + 1
        existing_req.last_requested_at = now
        if title_val:
            existing_req.title = title_val
        if authors_str:
            existing_req.authors = authors_str
        if num_pages_val is not None:
            existing_req.num_pages = num_pages_val
        db.add(existing_req)
    else:
        new_req = RequestedPaperRow(
            arxiv_id=arxiv_id,
            arxiv_abs_url=abs_url,
            arxiv_pdf_url=pdf_url,
            request_count=1,
            first_requested_at=now,
            last_requested_at=now,
            title=title_val,
            authors=authors_str,
            num_pages=num_pages_val,
        )
        db.add(new_req)
    db.commit()

    # Otherwise, just acknowledge the request without exposing queue state
    return RequestArxivResponse(state="requested")


class RequestedPaperItem(BaseModel):
    arxiv_id: str
    arxiv_abs_url: str
    arxiv_pdf_url: str
    request_count: int
    first_requested_at: datetime
    last_requested_at: datetime
    title: Optional[str] = None
    authors: Optional[str] = None
    num_pages: Optional[int] = None


@router.get("/requested_papers", response_model=List[RequestedPaperItem])
def list_requested_papers(include_processed: bool = False, db: Session = Depends(get_session), _admin: bool = Depends(require_admin)):
    q = db.query(RequestedPaperRow)
    if not include_processed:
        q = q.filter(RequestedPaperRow.processed == False)  # noqa: E712
    rows = q.order_by(RequestedPaperRow.last_requested_at.desc()).all()
    return [
        RequestedPaperItem(
            arxiv_id=r.arxiv_id,
            arxiv_abs_url=r.arxiv_abs_url,
            arxiv_pdf_url=r.arxiv_pdf_url,
            request_count=int(r.request_count or 0),
            first_requested_at=r.first_requested_at,
            last_requested_at=r.last_requested_at,
            title=r.title,
            authors=r.authors,
            num_pages=r.num_pages,
        )
        for r in rows
    ]


class StartProcessingResponse(BaseModel):
    paper_uuid: str
    status: str


@router.post("/requested_papers/{arxiv_id_or_url}/start_processing", response_model=StartProcessingResponse)
async def start_processing_requested(arxiv_id_or_url: str, db: Session = Depends(get_session), _admin: bool = Depends(require_admin)):
    # Normalize to base id
    try:
        norm = await normalize_id(arxiv_id_or_url)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid arXiv id or URL")
    base_id = norm.arxiv_id
    version = norm.version

    # Ensure request row exists; if not, create one
    req = db.query(RequestedPaperRow).filter(RequestedPaperRow.arxiv_id == base_id).first()
    now = datetime.utcnow()
    if not req:
        req = RequestedPaperRow(
            arxiv_id=base_id,
            arxiv_abs_url=f"https://arxiv.org/abs/{base_id}",
            arxiv_pdf_url=f"https://arxiv.org/pdf/{base_id}.pdf",
            request_count=1,
            first_requested_at=now,
            last_requested_at=now,
            processed=False,
        )
        db.add(req)
        db.flush()

    # Check if paper already exists in DB
    job = db.query(PaperRow).filter(PaperRow.arxiv_id == base_id).first()
    if job:
        # Do not modify existing job; return its identity
        return StartProcessingResponse(paper_uuid=job.paper_uuid, status=job.status)

    # Create new papers row with status 'not_started'
    paper_uuid = str(uuid.uuid4())
    new_job = PaperRow(
        paper_uuid=paper_uuid,
        arxiv_id=base_id,
        arxiv_version=version,
        arxiv_url=f"https://arxiv.org/abs/{base_id}{version or ''}",
        status="not_started",
        created_at=now,
        updated_at=now,
    )
    db.add(new_job)
    db.commit()
    db.refresh(new_job)
    return StartProcessingResponse(paper_uuid=new_job.paper_uuid, status=new_job.status)


class DeleteRequestedResponse(BaseModel):
    deleted: str


@router.delete("/requested_papers/{arxiv_id_or_url}", response_model=DeleteRequestedResponse)
async def delete_requested_paper(arxiv_id_or_url: str, db: Session = Depends(get_session), _admin: bool = Depends(require_admin)):
    try:
        norm = await normalize_id(arxiv_id_or_url)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid arXiv id or URL")
    base_id = norm.arxiv_id
    row = db.query(RequestedPaperRow).filter(RequestedPaperRow.arxiv_id == base_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Requested paper not found")
    db.delete(row)
    db.commit()
    return DeleteRequestedResponse(deleted=base_id)


# --- Email Notifications ---

class EmailNotificationItem(BaseModel):
    id: int
    email: str
    arxiv_id: str
    requested_at: datetime
    notified: bool


@router.get("/notifications/new_paper", response_model=List[EmailNotificationItem])
def list_new_paper_notifications(db: Session = Depends(get_session), _admin: bool = Depends(require_admin)):
    rows = db.query(NewPaperNotification).order_by(NewPaperNotification.requested_at.desc()).all()
    return [
        EmailNotificationItem(
            id=r.id,
            email=r.email,
            arxiv_id=r.arxiv_id,
            requested_at=r.requested_at,
            notified=r.notified,
        ) for r in rows
    ]


# --- Import worker-generated JSON into DB and filesystem ---

def _derive_arxiv_version_from_url(arxiv_url: Optional[str]) -> Optional[str]:
    if not arxiv_url:
        return None
    try:
        # Expect formats like https://arxiv.org/abs/<id>v3 (optional version)
        m = re.search(r"/abs/[^/]+?(v\d+)$", arxiv_url)
        if m:
            return m.group(1)
        return None
    except Exception:
        return None


class ImportResult(BaseModel):
    paper_uuid: str
    status: str


@router.post("/papers/import_json", response_model=JobDbStatus)
def import_paper_json(paper: Dict[str, Any], db: Session = Depends(get_session), _admin: bool = Depends(require_admin)):
    # Validate minimal required fields
    paper_id = paper.get("paper_id")
    arxiv_id = paper.get("arxiv_id")
    if not isinstance(paper_id, str) or not paper_id:
        raise HTTPException(status_code=400, detail="paper_id is required in JSON")
    if not isinstance(arxiv_id, str) or not arxiv_id:
        raise HTTPException(status_code=400, detail="arxiv_id is required in JSON")

    title = paper.get("title") if isinstance(paper.get("title"), str) else None
    authors = paper.get("authors") if isinstance(paper.get("authors"), str) else None
    arxiv_url_val = paper.get("arxiv_url") if isinstance(paper.get("arxiv_url"), str) else None
    arxiv_version_val = _derive_arxiv_version_from_url(arxiv_url_val)
    thumbnail_data_url = paper.get("thumbnail_data_url") if isinstance(paper.get("thumbnail_data_url"), str) else None
    pages = paper.get("pages") if isinstance(paper.get("pages"), list) else []
    num_pages = len(pages)
    processing_time_seconds = paper.get("processing_time_seconds")
    if not isinstance(processing_time_seconds, (int, float)):
        processing_time_seconds = None
    usage_summary = paper.get("usage_summary") or {}
    total_cost = usage_summary.get("total_cost") if isinstance(usage_summary, dict) else None
    if not isinstance(total_cost, (int, float)):
        total_cost = None
    avg_cost_per_page = None
    try:
        if total_cost is not None and num_pages > 0:
            avg_cost_per_page = float(total_cost) / float(num_pages)
    except Exception:
        avg_cost_per_page = None

    now = datetime.utcnow()

    # Upsert by arxiv_id
    existing = db.query(PaperRow).filter(PaperRow.arxiv_id == arxiv_id).first()
    if existing:
        target_uuid = existing.paper_uuid
        # Update existing row to completed
        existing.status = "completed"
        existing.error_message = None
        existing.updated_at = now
        existing.finished_at = now
        existing.title = title
        existing.authors = authors
        existing.arxiv_url = arxiv_url_val
        existing.arxiv_version = arxiv_version_val
        existing.num_pages = num_pages
        existing.processing_time_seconds = processing_time_seconds
        existing.total_cost = total_cost
        existing.avg_cost_per_page = avg_cost_per_page
        existing.thumbnail_data_url = thumbnail_data_url
        db.add(existing)
        db.flush()
        target_paper_row = existing
    else:
        # Ensure paper_uuid uniqueness; if collides with another arxiv_id, generate a new one
        target_uuid = paper_id
        by_uuid = db.query(PaperRow).filter(PaperRow.paper_uuid == target_uuid).first()
        if by_uuid and by_uuid.arxiv_id != arxiv_id:
            target_uuid = str(uuid.uuid4())
        new_row = PaperRow(
            paper_uuid=target_uuid,
            arxiv_id=arxiv_id,
            arxiv_version=arxiv_version_val,
            arxiv_url=arxiv_url_val,
            title=title,
            authors=authors,
            status="completed",
            error_message=None,
            created_at=now,
            updated_at=now,
            started_at=None,
            finished_at=now,
            num_pages=num_pages,
            processing_time_seconds=processing_time_seconds,
            total_cost=total_cost,
            avg_cost_per_page=avg_cost_per_page,
            thumbnail_data_url=thumbnail_data_url,
        )
        db.add(new_row)
        db.flush()
        target_paper_row = new_row

    # Mark requested paper as processed, if exists
    try:
        req = db.query(RequestedPaperRow).filter(RequestedPaperRow.arxiv_id == arxiv_id).first()
        if req and not getattr(req, 'processed', False):
            req.processed = True
            db.add(req)
    except Exception:
        logger.exception("Failed to mark requested paper as processed for arxiv_id=%s", arxiv_id)

    # Create slug on import; require title/authors; error on collision
    try:
        slug = _build_slug_from_title_and_authors(title, authors)
        exists = db.query(PaperSlugRow).filter(PaperSlugRow.slug == slug).first()
        if exists:
            raise HTTPException(status_code=409, detail="Slug already exists")
        db.add(PaperSlugRow(slug=slug, paper_uuid=target_paper_row.paper_uuid, tombstone=False, created_at=now))
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to create slug for imported paper %s", target_paper_row.paper_uuid)

    db.commit()

    # Persist JSON to data/paperjsons using the chosen UUID; optionally normalize paper_id inside file
    try:
        base_dir = os.path.abspath(os.path.join(os.getcwd(), 'data', 'paperjsons'))
        os.makedirs(base_dir, exist_ok=True)
        target_path = os.path.join(base_dir, f"{target_uuid}.json")
        # Ensure the internal paper_id matches the filename/DB UUID
        if paper.get('paper_id') != target_uuid:
            paper = dict(paper)
            paper['paper_id'] = target_uuid
        import json as _json
        with open(target_path, 'w', encoding='utf-8') as f:
            _json.dump(paper, f, ensure_ascii=False)
    except Exception:
        logger.exception("Failed to write imported JSON for paper_uuid=%s", target_uuid)

    # Return the DB row
    job = db.query(PaperRow).filter(PaperRow.paper_uuid == target_uuid).first()
    if not job:
        raise HTTPException(status_code=500, detail="Import completed but record not found")
    return JobDbStatus(
        paper_uuid=job.paper_uuid,
        status=job.status,
        error_message=job.error_message,
        created_at=job.created_at,
        updated_at=job.updated_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        arxiv_id=job.arxiv_id,
        arxiv_version=job.arxiv_version,
        arxiv_url=job.arxiv_url,
        title=job.title,
        authors=job.authors,
        num_pages=job.num_pages,
        thumbnail_data_url=getattr(job, 'thumbnail_data_url', None),
        processing_time_seconds=job.processing_time_seconds,
        total_cost=job.total_cost,
        avg_cost_per_page=job.avg_cost_per_page,
    )


# --- Slug generation and resolution ---

def _slugify_value(value: str) -> str:
    # Lowercase, strip accents, keep alnum and hyphen
    try:
        import unicodedata
        value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    except Exception:
        value = value
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip('-')
    return value[:120]


def _build_slug_from_title_and_authors(title: Optional[str], authors: Optional[str]) -> str:
    if not title or not authors:
        raise HTTPException(status_code=400, detail="Cannot generate slug without title and authors")
    # Limit title to the first 12 words
    try:
        title_tokens = [t for t in (title or '').split() if t]
    except Exception:
        title_tokens = []
    limited_title = " ".join(title_tokens[:12]) if title_tokens else title
    # Take up to two authors, using last names when possible
    author_list = [a.strip() for a in authors.split(',') if a.strip()]
    if len(author_list) == 0:
        raise HTTPException(status_code=400, detail="Cannot generate slug: no authors present")
    use_authors = author_list[:2]
    def last_name(full: str) -> str:
        parts = full.split()
        return parts[-1] if parts else full
    author_bits = [last_name(a) for a in use_authors]
    base = f"{limited_title} {' '.join(author_bits)}"
    return _slugify_value(base)


class ResolveSlugResponse(BaseModel):
    paper_uuid: Optional[str]
    slug: str
    tombstone: bool


@router.get("/papers/slug/{slug}", response_model=ResolveSlugResponse)
def resolve_slug(slug: str, db: Session = Depends(get_session)):
    logger.info("GET /papers/slug/%s", slug)
    row = db.query(PaperSlugRow).filter(PaperSlugRow.slug == slug).first()
    if not row:
        logger.warning("Slug not found slug=%s", slug)
        raise HTTPException(status_code=404, detail="Slug not found")
    logger.info("Resolved slug=%s -> paper_uuid=%s tombstone=%s", slug, row.paper_uuid, bool(getattr(row, 'tombstone', False)))
    return ResolveSlugResponse(paper_uuid=row.paper_uuid, slug=row.slug, tombstone=bool(getattr(row, 'tombstone', False)))


class CreateSlugRequest(BaseModel):
    paper_uuid: str


@router.post("/papers/{paper_uuid}/slug", response_model=ResolveSlugResponse)
def create_slug(paper_uuid: UUID, db: Session = Depends(get_session)):
    # Load paper and validate required metadata
    logger.info("POST /papers/%s/slug (create)", paper_uuid)
    job = db.query(PaperRow).filter(PaperRow.paper_uuid == str(paper_uuid)).first()
    if not job:
        logger.warning("Cannot create slug: paper not found paper_uuid=%s", paper_uuid)
        raise HTTPException(status_code=404, detail="Paper not found")
    slug = _build_slug_from_title_and_authors(job.title, job.authors)
    # Enforce uniqueness strictly; on collision, throw 409
    existing = db.query(PaperSlugRow).filter(PaperSlugRow.slug == slug).first()
    if existing:
        raise HTTPException(status_code=409, detail="Slug already exists")
    row = PaperSlugRow(slug=slug, paper_uuid=paper_uuid, tombstone=False, created_at=datetime.utcnow())
    db.add(row)
    db.commit()
    db.refresh(row)
    return ResolveSlugResponse(paper_uuid=row.paper_uuid, slug=row.slug, tombstone=bool(row.tombstone))


@router.get("/papers/{paper_uuid}/slug", response_model=ResolveSlugResponse)
def get_slug_for_paper(paper_uuid: UUID, db: Session = Depends(get_session)):
    # Return latest non-tombstone slug for this paper
    logger.info("GET /papers/%s/slug", paper_uuid)
    row = (
        db.query(PaperSlugRow)
        .filter(PaperSlugRow.paper_uuid == str(paper_uuid))
        .filter(PaperSlugRow.tombstone == False)  # noqa: E712
        .order_by(PaperSlugRow.created_at.desc())
        .first()
    )
    if not row:
        logger.warning("Slug not found for paper_uuid=%s", paper_uuid)
        raise HTTPException(status_code=404, detail="Slug not found for paper")
    logger.info("Resolved latest slug for paper_uuid=%s -> slug=%s", paper_uuid, row.slug)
    return ResolveSlugResponse(paper_uuid=row.paper_uuid, slug=row.slug, tombstone=False)


# --- Minimal papers listing (for All Papers and Similar sidebar) ---

def _paperjsons_dir() -> str:
    return os.path.abspath(os.path.join(os.getcwd(), "data", "paperjsons"))


def _build_dir_fingerprint(dir_path: str) -> str:
    try:
        entries = []
        for name in os.listdir(dir_path):
            if not name.lower().endswith(".json"):
                continue
            p = os.path.join(dir_path, name)
            try:
                st = os.stat(p)
                entries.append((name, int(st.st_mtime_ns), int(st.st_size)))
            except FileNotFoundError:
                # File might disappear between listdir and stat; ignore
                continue
        entries.sort()
        h = hashlib.sha256()
        for name, mtime, size in entries:
            h.update(name.encode("utf-8", errors="ignore"))
            h.update(str(mtime).encode("ascii"))
            h.update(str(size).encode("ascii"))
        return h.hexdigest()
    except Exception:
        logger.exception("Failed to build fingerprint for %s", dir_path)
        return ""


def _scan_minimal_items(dir_path: str) -> List[MinimalPaperItem]:
    items: List[MinimalPaperItem] = []
    try:
        files = [f for f in os.listdir(dir_path) if f.lower().endswith('.json')]
        files.sort()
    except FileNotFoundError:
        return []
    for name in files:
        try:
            paper_uuid = re.sub(r"\.json$", "", name, flags=re.IGNORECASE)
            with open(os.path.join(dir_path, name), 'r', encoding='utf-8') as f:
                data = _json.load(f)
            title = data.get('title') if isinstance(data.get('title'), str) else None
            authors = data.get('authors') if isinstance(data.get('authors'), str) else None
            thumb = data.get('thumbnail_data_url') if isinstance(data.get('thumbnail_data_url'), str) else None
            items.append(MinimalPaperItem(paper_uuid=paper_uuid, title=title, authors=authors, thumbnail_data_url=thumb))
        except Exception:
            logger.exception("Failed to read minimal fields from %s", name)
            continue
    return items



from functools import lru_cache

@lru_cache(maxsize=64)
def _get_minimal_items_for_fingerprint(_fp: str, dir_path: str) -> List[MinimalPaperItem]:
    """
    Cache the minimal scan results per directory fingerprint. The first argument
    is the fingerprint and is intentionally unused except to key the cache.
    """
    logger.info("Scanning minimal items for fp=%s dir=%s", _fp, dir_path)
    items = _scan_minimal_items(dir_path)
    logger.info("Scanned minimal items count=%d for fp=%s", len(items), _fp)
    return items