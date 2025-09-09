import logging
import time
from typing import Dict, Any, List, Optional
import os
import io
import base64
import json
from PIL import Image
import asyncio
from concurrent.futures import ThreadPoolExecutor
import re


from shared.openrouter import client as openrouter
# Note: Do not import from api.* here to keep layering clean
from shared.arxiv.client import (
    normalize_id as arxiv_normalize_id,
    fetch_metadata as arxiv_fetch_metadata,
)
from shared.db import SessionLocal
from papers.models import PaperRow

# --- Shared helpers for other layers (worker/endpoints) ---

def build_paper_slug(title: Optional[str], authors: Optional[str]) -> str:
    """
    Build a stable, URL-safe slug from title and authors.

    Rules:
    - Require both title and authors; raise ValueError otherwise
    - Use first 12 words of title
    - Append up to two author last names
    - ASCII only, lowercase, hyphen-separated; max length ~120
    """
    if not title or not authors:
        raise ValueError("Cannot generate slug without title and authors")

    def _slugify_value(value: str) -> str:
        try:
            import unicodedata
            value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
        except Exception:
            value = value
        import re as _re
        value = value.lower()
        value = _re.sub(r"[^a-z0-9]+", "-", value)
        value = _re.sub(r"-+", "-", value).strip('-')
        return value[:120]

    try:
        title_tokens = [t for t in (title or '').split() if t]
    except Exception:
        title_tokens = []
    limited_title = " ".join(title_tokens[:12]) if title_tokens else (title or "")

    try:
        author_list = [a.strip() for a in (authors or '').split(',') if a.strip()]
    except Exception:
        author_list = []
    if len(author_list) == 0:
        raise ValueError("Cannot generate slug: no authors present")

    use_authors = author_list[:2]

    def _last_name(full: str) -> str:
        parts = full.split()
        return parts[-1] if parts else full

    author_bits = [_last_name(a) for a in use_authors]
    base = f"{limited_title} {' '.join(author_bits)}".strip()
    return _slugify_value(base)


def get_processed_result_path(paper_uuid: str) -> str:
    """
    Return absolute filesystem path for the stored processed result JSON for a paper.
    Directory is controlled by env PAPER_JSON_DIR (default: data/paperjsons/).
    """
    base_dir = os.path.abspath(os.environ.get("PAPER_JSON_DIR", os.path.join(os.getcwd(), 'data', 'paperjsons')))
    return os.path.join(base_dir, f"{paper_uuid}.json")


def store_processed_result(paper_uuid: str, result: Dict[str, Any]) -> str:
    """
    Persist the processed result as JSON for the given paper UUID.
    - Ensures directory exists
    - Atomic write via temp file + os.replace
    - UTF-8 with ensure_ascii=False
    Returns the final file path.
    """
    target_path = get_processed_result_path(paper_uuid)
    target_dir = os.path.dirname(target_path)
    os.makedirs(target_dir, exist_ok=True)
    tmp_path = f"{target_path}.tmp"
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False)
    os.replace(tmp_path, target_path)
    return target_path


# --- Processing status helpers ---

def get_paper_status_by_uuid(paper_uuid: str) -> Optional[str]:
    """
    Return the current status string for a paper UUID from the DB, or None if not found.
    Status values include: 'not_started', 'processing', 'completed', 'failed'.
    """
    session = SessionLocal()
    try:
        row = session.query(PaperRow).filter(PaperRow.paper_uuid == str(paper_uuid)).first()
        return row.status if row else None
    finally:
        session.close()


def is_paper_processing_by_uuid(paper_uuid: str) -> bool:
    """
    True if the paper exists and its status is 'processing'.
    """
    status = get_paper_status_by_uuid(paper_uuid)
    return status == 'processing'


async def get_paper_status_by_arxiv_id_or_url(arxiv_id_or_url: str) -> Optional[str]:
    """
    Normalize an arXiv id or URL and return the paper status by arXiv id, or None if not found.
    """
    norm = await arxiv_normalize_id(arxiv_id_or_url)
    base_id = norm.arxiv_id
    session = SessionLocal()
    try:
        row = session.query(PaperRow).filter(PaperRow.arxiv_id == base_id).first()
        return row.status if row else None
    finally:
        session.close()


async def is_paper_processing_for_arxiv(arxiv_id_or_url: str) -> bool:
    """
    True if a paper for this arXiv id/URL exists and is currently 'processing'.
    """
    status = await get_paper_status_by_arxiv_id_or_url(arxiv_id_or_url)
    return status == 'processing'


# --- Processing metrics helpers ---

def _load_usage_summary_from_json(paper_uuid: str) -> Optional[Dict[str, Any]]:
    try:
        path = get_processed_result_path(paper_uuid)
        if not os.path.exists(path):
            return None
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        us = data.get('usage_summary')
        return us if isinstance(us, dict) else None
    except Exception:
        return None


def get_processing_metrics_for_user(paper_uuid: str, auth_provider_id: str) -> Dict[str, Any]:
    """
    Return processing metrics for a completed paper to the initiating user only.
    Raises PermissionError if caller is not the initiator.
    """
    session = SessionLocal()
    try:
        row: PaperRow | None = session.query(PaperRow).filter(PaperRow.paper_uuid == str(paper_uuid)).first()
        if not row:
            raise FileNotFoundError("Paper not found")
        if row.status != 'completed':
            raise RuntimeError("Paper not completed")
        if not row.initiated_by_user_id or row.initiated_by_user_id != auth_provider_id:
            raise PermissionError("Not authorized to view metrics for this paper")
        usage_summary = _load_usage_summary_from_json(row.paper_uuid)
        return {
            "paper_uuid": row.paper_uuid,
            "status": row.status,
            "created_at": row.created_at,
            "started_at": row.started_at,
            "finished_at": row.finished_at,
            "num_pages": row.num_pages,
            "processing_time_seconds": row.processing_time_seconds,
            "total_cost": row.total_cost,
            "avg_cost_per_page": row.avg_cost_per_page,
            "usage_summary": usage_summary,
        }
    finally:
        session.close()


def get_processing_metrics_for_admin(paper_uuid: str) -> Dict[str, Any]:
    """
    Return processing metrics for a completed paper for admin usage. No initiator check.
    """
    session = SessionLocal()
    try:
        row: PaperRow | None = session.query(PaperRow).filter(PaperRow.paper_uuid == str(paper_uuid)).first()
        if not row:
            raise FileNotFoundError("Paper not found")
        if row.status != 'completed':
            raise RuntimeError("Paper not completed")
        usage_summary = _load_usage_summary_from_json(row.paper_uuid)
        return {
            "paper_uuid": row.paper_uuid,
            "status": row.status,
            "created_at": row.created_at,
            "started_at": row.started_at,
            "finished_at": row.finished_at,
            "num_pages": row.num_pages,
            "processing_time_seconds": row.processing_time_seconds,
            "total_cost": row.total_cost,
            "avg_cost_per_page": row.avg_cost_per_page,
            "usage_summary": usage_summary,
            "initiated_by_user_id": row.initiated_by_user_id,
        }
    finally:
        session.close()
