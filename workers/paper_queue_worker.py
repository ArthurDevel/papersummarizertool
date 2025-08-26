from __future__ import annotations

import asyncio
import logging
import os
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from shared.db import SessionLocal
from papers.models import PaperRow, RequestedPaperRow, PaperSlugRow
from shared.arxiv.client import fetch_pdf_for_processing
from paperprocessor.client import process_paper_pdf, build_paper_slug, store_processed_result


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("paper_queue_worker")


@contextmanager
def session_scope():
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


async def _process_one(job: PaperRow) -> None:
    logger.info("Processing job id=%s paper_uuid=%s arxiv=%s", job.id, job.paper_uuid, job.arxiv_id)
    try:
        pdf = await fetch_pdf_for_processing(job.arxiv_url or job.arxiv_id)
        result = await process_paper_pdf(pdf.pdf_bytes, paper_id=job.paper_uuid, arxiv_id_or_url=(job.arxiv_url or job.arxiv_id))

        # Persist processed result via processor helper
        store_processed_result(job.paper_uuid, result)

        # Read metrics directly from result (computed by processor)
        num_pages = result.get('num_pages')
        processing_time = result.get('processing_time_seconds')
        total_cost = result.get('total_cost')
        avg_cost_per_page = result.get('avg_cost_per_page')

        with session_scope() as s:
            j = s.get(PaperRow, job.id, with_for_update=True)
            if not j:
                return
            j.status = 'completed'
            j.finished_at = datetime.utcnow()
            j.updated_at = datetime.utcnow()
            j.num_pages = num_pages
            j.processing_time_seconds = processing_time
            j.total_cost = total_cost
            j.avg_cost_per_page = avg_cost_per_page
            # Persist title and authors (strings) if available; else set to None
            j.title = result.get('title') if isinstance(result.get('title'), str) else None
            j.authors = result.get('authors') if isinstance(result.get('authors'), str) else None
            thumb_val = result.get('thumbnail_data_url')
            j.thumbnail_data_url = thumb_val if isinstance(thumb_val, str) else None
            s.add(j)
            # Create slug on completion; strict: require title and authors; throw on collision
            try:
                slug = build_paper_slug(j.title, j.authors)
                exists = s.query(PaperSlugRow).filter(PaperSlugRow.slug == slug).first()
                if exists:
                    raise ValueError(f"Slug collision for '{slug}'")
                s.add(PaperSlugRow(slug=slug, paper_uuid=j.paper_uuid, tombstone=False, created_at=datetime.utcnow()))
            except Exception:
                logger.exception("Failed to create slug for paper_uuid=%s", j.paper_uuid)
            # Mark corresponding request as processed (soft-delete)
            try:
                req = s.query(RequestedPaperRow).filter(RequestedPaperRow.arxiv_id == (j.arxiv_id)).first()
                if req and not getattr(req, 'processed', False):
                    req.processed = True
                    s.add(req)
            except Exception:
                logger.exception("Failed to mark requested paper as processed for arxiv_id=%s", j.arxiv_id)
    except Exception as e:
        logger.exception("Job %s failed", job.id)
        with session_scope() as s:
            j = s.get(PaperRow, job.id, with_for_update=True)
            if not j:
                return
            j.status = 'failed'
            j.error_message = str(e)
            j.finished_at = datetime.utcnow()
            j.updated_at = datetime.utcnow()
            s.add(j)


def _claim_next_job() -> Optional[PaperRow]:
    # Use a transaction and SELECT ... FOR UPDATE SKIP LOCKED to avoid contention
    with session_scope() as s:
        # MySQL 8 supports SKIP LOCKED
        row = s.execute(
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
        if not row:
            return None
        job: PaperRow = s.get(PaperRow, row[0], with_for_update=True)
        if not job:
            return None
        job.status = 'processing'
        job.started_at = datetime.utcnow()
        job.updated_at = datetime.utcnow()
        s.add(job)
        # After commit, return a detached copy (refresh to load values)
        s.flush()
        s.expunge(job)
        return job


async def worker_loop():
    logger.info("Paper queue worker started")
    while True:
        try:
            job = _claim_next_job()
            if not job:
                await asyncio.sleep(60)
                continue
            await _process_one(job)
        except Exception:
            logger.exception("Worker loop error; sleeping")
            await asyncio.sleep(10)


def main():
    asyncio.run(worker_loop())


if __name__ == "__main__":
    main()


