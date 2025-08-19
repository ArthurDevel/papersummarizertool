from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Response, status, Depends
from typing import Union, List, Optional
from pydantic import BaseModel
from sqlalchemy.orm import Session
from api.types.paper_processing_api_models import Paper, JobStatusResponse
from paperprocessor.client import process_paper_pdf
from shared.db import get_session
from api.models import PaperRow
from shared.arxiv.client import normalize_id
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
    num_pages: int | None = None
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
        num_pages=job.num_pages,
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
            num_pages=r.num_pages,
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