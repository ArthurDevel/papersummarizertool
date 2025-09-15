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
from papers.models import Paper, PaperSlug
from papers.client import get_paper_metadata, save_paper
from papers.db.models import PaperRecord, PaperSlugRecord
from shared.arxiv.client import fetch_pdf_for_processing
from paperprocessor.client import process_paper_pdf_legacy
from users.client import set_requests_processed


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


async def _process_one(job: PaperRecord) -> None:
    logger.info("Processing job id=%s paper_uuid=%s arxiv=%s", job.id, job.paper_uuid, job.arxiv_id)
    try:
        pdf = await fetch_pdf_for_processing(job.arxiv_url or job.arxiv_id)
        result = await process_paper_pdf_legacy(pdf.pdf_bytes, paper_id=job.paper_uuid)

        # Persist processed result JSON (avoid v1 import)
        _store_processed_result(job.paper_uuid, result)

        # Read metrics directly from result (computed by processor)
        num_pages = result.get('num_pages')
        processing_time = result.get('processing_time_seconds')
        total_cost = result.get('total_cost')
        avg_cost_per_page = result.get('avg_cost_per_page')

        with session_scope() as s:
            j = s.get(PaperRecord, job.id, with_for_update=True)
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
            # Create slug on completion; idempotent for same paper, strict for true collisions
            try:
                # If this paper already has a non-tombstoned slug, reuse it (idempotent restart)
                existing_for_paper = (
                    s.query(PaperSlugRecord)
                    .filter(PaperSlugRecord.paper_uuid == j.paper_uuid, PaperSlugRecord.tombstone == False)  # noqa: E712
                    .order_by(PaperSlugRecord.created_at.desc())
                    .first()
                )
                if existing_for_paper:
                    slug = existing_for_paper.slug
                else:
                    slug = _build_paper_slug(j.title, j.authors)
                    exists = s.query(PaperSlugRecord).filter(PaperSlugRecord.slug == slug).first()
                    if exists:
                        # If slug already maps to this paper, reuse; otherwise it's a true collision
                        if exists.paper_uuid != j.paper_uuid:
                            raise ValueError(f"Slug collision for '{slug}'")
                        # Reuse without inserting a duplicate row
                    else:
                        s.add(PaperSlugRecord(slug=slug, paper_uuid=j.paper_uuid, tombstone=False, created_at=datetime.utcnow()))
            except Exception:
                logger.exception("Failed to create slug for paper_uuid=%s", j.paper_uuid)
                raise
            # After slug is added in the same transaction, mark user requests processed.
            # This requires slug; if it fails, let it bubble up (no backfill).
            s.flush()
            await set_requests_processed(s, j.arxiv_id, slug)
    except Exception as e:
        logger.exception("Job %s failed", job.id)
        with session_scope() as s:
            j = s.get(PaperRecord, job.id, with_for_update=True)
            if not j:
                return
            j.status = 'failed'
            j.error_message = str(e)
            j.finished_at = datetime.utcnow()
            j.updated_at = datetime.utcnow()
            s.add(j)


def _claim_next_job() -> Optional[PaperRecord]:
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
        job: PaperRecord = s.get(PaperRecord, row[0], with_for_update=True)
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




# --- Local helpers (remove v1 dependency) ---
def _get_processed_result_path(paper_uuid: str) -> str:
    base_dir = os.path.abspath(os.environ.get("PAPER_JSON_DIR", os.path.join(os.getcwd(), 'data', 'paperjsons')))
    return os.path.join(base_dir, f"{paper_uuid}.json")


def _store_processed_result(paper_uuid: str, result: dict) -> str:
    target_path = _get_processed_result_path(paper_uuid)
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    tmp_path = f"{target_path}.tmp"
    import json as _json
    with open(tmp_path, 'w', encoding='utf-8') as f:
        _json.dump(result, f, ensure_ascii=False)
    os.replace(tmp_path, target_path)
    return target_path


def _build_paper_slug(title: str | None, authors: str | None) -> str:
    if not title or not authors:
        raise ValueError("Cannot generate slug without title and authors")
    try:
        import unicodedata
        t = unicodedata.normalize('NFKD', title).encode('ascii', 'ignore').decode('ascii')
        a = unicodedata.normalize('NFKD', authors).encode('ascii', 'ignore').decode('ascii')
    except Exception:
        t, a = title, authors
    title_tokens = [tok for tok in (t or '').split() if tok][:12]
    author_list = [s.strip() for s in (a or '').split(',') if s.strip()]
    if not author_list:
        raise ValueError("Cannot generate slug: no authors present")
    def _last_name(full: str) -> str:
        parts = full.split()
        return parts[-1] if parts else full
    use_authors = author_list[:2]
    base = f"{' '.join(title_tokens) if title_tokens else t} {' '.join(_last_name(x) for x in use_authors)}".strip()
    import re as _re
    s = base.lower()
    s = _re.sub(r"[^a-z0-9]+", "-", s)
    s = _re.sub(r"-+", "-", s).strip('-')
    return s[:120]


def main():
    asyncio.run(worker_loop())


if __name__ == "__main__":
    main()