from __future__ import annotations

import asyncio
import logging
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from shared.db import SessionLocal
from papers.models import Paper
from papers.client import save_paper, create_paper_slug
from papers.db.models import PaperRecord
from shared.arxiv.client import fetch_pdf_for_processing
from paperprocessor.client import process_paper_pdf
from paperprocessor.models import ProcessedDocument
from users.client import set_requests_processed


### CONSTANTS ###

WORKER_SLEEP_SECONDS = 60
ERROR_SLEEP_SECONDS = 10


### LOGGING SETUP ###

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("paper_queue_worker")


### DATABASE HELPERS ###

@contextmanager
def database_session():
    """
    Create a database session with automatic commit/rollback handling.
    
    Yields:
        Session: SQLAlchemy session for database operations
        
    Raises:
        Exception: Any database error that occurs during the transaction
    """
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


### PAPER PROCESSING FUNCTIONS ###

async def _download_and_process_pdf(arxiv_identifier: str) -> ProcessedDocument:
    """
    Download PDF from arXiv and process it through the paper processing pipeline.
    
    Args:
        arxiv_identifier: arXiv ID or URL to download and process
        
    Returns:
        ProcessedDocument: Fully processed document with pages, sections, and images
        
    Raises:
        Exception: If PDF download or processing fails
    """
    logger.info("Downloading PDF for arXiv identifier: %s", arxiv_identifier)
    pdf_data = await fetch_pdf_for_processing(arxiv_identifier)
    
    logger.info("Processing PDF through pipeline")
    processed_document = await process_paper_pdf(pdf_data.pdf_bytes)
    
    return processed_document




def _mark_job_as_failed(job_id: int, error_message: str) -> None:
    """
    Mark a processing job as failed in the database.
    
    Args:
        job_id: ID of the job that failed
        error_message: Description of the failure
    """
    with database_session() as session:
        failed_job = session.get(PaperRecord, job_id, with_for_update=True)
        if not failed_job:
            logger.warning("Cannot mark job as failed - job %s not found", job_id)
            return
        
        # Update job status to failed
        failed_job.status = 'failed'
        failed_job.error_message = error_message
        failed_job.finished_at = datetime.utcnow()
        failed_job.updated_at = datetime.utcnow()
        session.add(failed_job)
        
        logger.info("Marked job %s as failed: %s", job_id, error_message)


async def _process_single_paper_job(job: PaperRecord) -> None:
    """
    Process a single paper job through the complete pipeline.
    
    Args:
        job: Paper processing job from the database
        
    Raises:
        Exception: If any step of processing fails
    """
    logger.info("Processing job id=%s paper_uuid=%s arxiv=%s", job.id, job.paper_uuid, job.arxiv_id)
    
    try:
        # Step 1: Download and process PDF
        processed_document = await _download_and_process_pdf(job.arxiv_url or job.arxiv_id)
        
        # Step 2: Add job metadata to processed document
        processed_document.paper_uuid = job.paper_uuid
        processed_document.arxiv_id = job.arxiv_id
        
        # Step 3: Save processed document to database and JSON file
        with database_session() as session:
            saved_paper = save_paper(session, processed_document)
            
            # Step 4: Create URL slug for the paper
            paper_slug_dto = create_paper_slug(session, saved_paper)
            
            # Step 5: Mark user requests as processed
            session.flush()  # Ensure slug is committed before marking requests
            await set_requests_processed(session, saved_paper.arxiv_id, paper_slug_dto.slug)
            
        logger.info("Successfully completed processing job %s", job.id)
        
    except Exception as error:
        logger.exception("Job %s failed during processing", job.id)
        _mark_job_as_failed(job.id, str(error))
        raise


### JOB MANAGEMENT FUNCTIONS ###

def _get_next_available_job() -> Optional[PaperRecord]:
    """
    Claim the next available job from the queue using database locking.
    
    Returns:
        Optional[PaperRecord]: Next job to process, or None if queue is empty
    """
    with database_session() as session:
        # Step 1: Find and lock next available job
        job_row = session.execute(
            text(
                """
                SELECT id FROM papers
                WHERE status = 'not_started'
                ORDER BY created_at ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED
                """
            )
        ).first()
        
        if not job_row:
            return None
        
        # Step 2: Load job record with lock
        job_record: PaperRecord = session.get(PaperRecord, job_row[0], with_for_update=True)
        if not job_record:
            logger.warning("Job row disappeared during locking: %s", job_row[0])
            return None
        
        # Step 3: Mark job as processing
        job_record.status = 'processing'
        job_record.started_at = datetime.utcnow()
        job_record.updated_at = datetime.utcnow()
        session.add(job_record)
        
        # Step 4: Commit changes and return detached job record
        session.flush()
        session.expunge(job_record)
        
        logger.info("Claimed job %s for processing", job_record.id)
        return job_record


### MAIN WORKER LOOP ###

async def run_paper_processing_worker() -> None:
    """
    Main worker loop that continuously processes paper jobs from the queue.
    
    This function runs indefinitely, checking for new jobs every 60 seconds
    when the queue is empty, and processing jobs as they become available.
    """
    logger.info("Paper queue worker started")
    
    while True:
        try:
            # Step 1: Try to get next job from queue
            next_job = _get_next_available_job()
            
            if not next_job:
                # Step 2: No jobs available - wait before checking again
                logger.debug("No jobs available, sleeping for %s seconds", WORKER_SLEEP_SECONDS)
                await asyncio.sleep(WORKER_SLEEP_SECONDS)
                continue
            
            # Step 3: Process the job
            await _process_single_paper_job(next_job)
            
        except Exception:
            # Step 4: Handle unexpected errors and continue running
            logger.exception("Worker loop encountered unexpected error, sleeping for %s seconds", ERROR_SLEEP_SECONDS)
            await asyncio.sleep(ERROR_SLEEP_SECONDS)


### MAIN ENTRY POINT ###

def main() -> None:
    """
    Main entry point for the paper queue worker.
    """
    asyncio.run(run_paper_processing_worker())


if __name__ == "__main__":
    main()