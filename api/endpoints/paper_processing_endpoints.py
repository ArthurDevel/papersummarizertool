from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Response, status, Depends
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from typing import Union, List, Optional, Dict, Any
from pydantic import BaseModel
from sqlalchemy.orm import Session
from api.types.paper_processing_api_models import Paper, JobStatusResponse, MinimalPaperItem
from api.types.paper_processing_endpoints import JobDbStatus
from paperprocessor.client import process_paper_pdf, get_processed_result_path, build_paper_slug
from shared.db import get_session
from papers.models import PaperRow, PaperSlugRow
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




# --- Slug generation and resolution ---


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