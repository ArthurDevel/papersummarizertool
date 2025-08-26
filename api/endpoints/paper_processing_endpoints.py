from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Response, status, Depends
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from typing import Union, List, Optional, Dict, Any
from pydantic import BaseModel
from sqlalchemy.orm import Session
from api.types.paper_processing_api_models import Paper, JobStatusResponse, MinimalPaperItem
from api.types.paper_processing_endpoints import JobDbStatus
from paperprocessor.client import process_paper_pdf, get_processed_result_path, build_paper_slug
from shared.db import get_session
from papers.models import PaperRow, RequestedPaperRow, PaperSlugRow, NewPaperNotification
from papers import client as papers_client
from shared.arxiv.client import normalize_id, parse_url, fetch_metadata, download_pdf
from shared.arxiv.models import ArxivMetadata
import os
import uuid
from datetime import datetime
from uuid import UUID
from api.background_jobs import create_job, get_job_status, update_job_status
import logging

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


## Moved JobDbStatus to api/types/paper_processing_endpoints.py


 
@router.get("/papers/minimal", response_model=List[MinimalPaperItem])
def list_minimal_papers(db: Session = Depends(get_session)):
    """
    Returns a minimal list of papers: paper_uuid, title, authors, thumbnail_data_url, slug.
    Delegates to papers.client.list_minimal_papers.
    """
    items = papers_client.list_minimal_papers(db)
    return items



@router.get("/papers/{paper_uuid}", response_model=JobDbStatus)
def get_paper_by_uuid(paper_uuid: UUID, db: Session = Depends(get_session)):
    logger.info("GET /papers/%s", paper_uuid)
    job = papers_client.get_paper_by_uuid(db, str(paper_uuid))
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


## Moved admin list endpoint to api/endpoints/admin.py


## Moved admin restart endpoint to api/endpoints/admin.py


## Moved admin delete endpoint to api/endpoints/admin.py


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
        json_path = get_processed_result_path(job.paper_uuid)
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
                slug_val = build_paper_slug(job.title, job.authors)
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





# --- Slug generation and resolution ---

## Removed private slug helpers; use build_paper_slug from paperprocessor.client


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
    slug = build_paper_slug(job.title, job.authors)
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