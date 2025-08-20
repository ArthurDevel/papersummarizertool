from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Response, status, Depends
from typing import Union, List, Optional
from pydantic import BaseModel
from sqlalchemy.orm import Session
from api.types.paper_processing_api_models import Paper, JobStatusResponse
from paperprocessor.client import process_paper_pdf
from shared.db import get_session
from api.models import PaperRow, RequestedPaperRow
from shared.arxiv.client import normalize_id, parse_url, fetch_metadata, head_pdf, download_pdf
import os
import uuid
from datetime import datetime
from api.background_jobs import create_job, get_job_status, update_job_status
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

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


@router.get("/papers/{paper_uuid}", response_model=JobDbStatus)
def get_paper_by_uuid(paper_uuid: str, db: Session = Depends(get_session)):
    job = db.query(PaperRow).filter(PaperRow.paper_uuid == paper_uuid).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
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
def list_papers(status: Optional[str] = None, limit: int = 500, db: Session = Depends(get_session)):
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
def restart_paper(paper_uuid: str, _body: RestartPaperRequest | None = None, db: Session = Depends(get_session)):
    row = db.query(PaperRow).filter(PaperRow.paper_uuid == paper_uuid).first()
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
def delete_paper(paper_uuid: str, db: Session = Depends(get_session)):
    row = db.query(PaperRow).filter(PaperRow.paper_uuid == paper_uuid).first()
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
    db.commit()
    return {"deleted": paper_uuid}


# --- Request Paper (strict arXiv URL) ---

class RequestArxivRequest(BaseModel):
    url: str


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

    # If the paper exists and is completed with JSON available, return viewer URL and DO NOT add to requests
    job = db.query(PaperRow).filter(PaperRow.arxiv_id == arxiv_id).first()
    if job and job.status == "completed":
        base_dir = os.path.abspath(os.path.join(os.getcwd(), 'data', 'paperjsons'))
        json_path = os.path.join(base_dir, f"{job.paper_uuid}.json")
        if os.path.exists(json_path):
            return RequestArxivResponse(state="exists", viewer_url=f"/?file={job.paper_uuid}.json")

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
def list_requested_papers(include_processed: bool = False, db: Session = Depends(get_session)):
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
async def start_processing_requested(arxiv_id_or_url: str, db: Session = Depends(get_session)):
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
async def delete_requested_paper(arxiv_id_or_url: str, db: Session = Depends(get_session)):
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