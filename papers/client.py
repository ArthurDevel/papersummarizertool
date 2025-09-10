from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from typing import Any, Dict, List, Optional
import hashlib
import json as _json
import os
import re
import unicodedata

from sqlalchemy.orm import Session

from papers.models import PaperRow, PaperSlugRow
from paperprocessor.client import get_processed_result_path


### HELPER FUNCTIONS ###

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
            value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
        except Exception:
            value = value
        value = value.lower()
        value = re.sub(r"[^a-z0-9]+", "-", value)
        value = re.sub(r"-+", "-", value).strip('-')
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


### MAIN FUNCTIONS ###

def get_paper_by_uuid(db: Session, paper_uuid: str) -> Optional[PaperRow]:
    return db.query(PaperRow).filter(PaperRow.paper_uuid == str(paper_uuid)).first()


def list_papers(db: Session, statuses: Optional[List[str]], limit: int) -> List[PaperRow]:
    q = db.query(PaperRow)
    if statuses:
        q = q.filter(PaperRow.status.in_(statuses))
    q = q.order_by(PaperRow.created_at.desc()).limit(max(1, min(limit, 1000)))
    return q.all()


def _paperjsons_dir() -> str:
    # Reuse processor's path helper to determine directory
    sample_path = get_processed_result_path("sample")
    return os.path.dirname(sample_path)


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
                continue
        entries.sort()
        h = hashlib.sha256()
        for name, mtime, size in entries:
            h.update(name.encode("utf-8", errors="ignore"))
            h.update(str(mtime).encode("ascii"))
            h.update(str(size).encode("ascii"))
        return h.hexdigest()
    except Exception:
        return ""


def _scan_minimal_items(dir_path: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
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
            items.append({
                "paper_uuid": paper_uuid,
                "title": title,
                "authors": authors,
                "thumbnail_data_url": thumb,
            })
        except Exception:
            continue
    return items


@lru_cache(maxsize=64)
def _get_minimal_items_for_fingerprint(_fp: str, dir_path: str) -> List[Dict[str, Any]]:
    return _scan_minimal_items(dir_path)


def list_minimal_papers(db: Session) -> List[Dict[str, Any]]:
    base_dir = _paperjsons_dir()
    fp = _build_dir_fingerprint(base_dir)
    items = _get_minimal_items_for_fingerprint(fp, base_dir) if fp else []

    # Merge slug mapping (latest non-tombstone per paper_uuid)
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

    for it in items:
        m = latest_by_uuid.get(it["paper_uuid"]) if isinstance(it, dict) else None
        if m:
            it["slug"] = m["slug"]

    return items


def delete_paper(db: Session, paper_uuid: str) -> bool:
    row = db.query(PaperRow).filter(PaperRow.paper_uuid == str(paper_uuid)).first()
    if not row:
        return False

    # Delete JSON file if exists
    try:
        json_path = get_processed_result_path(str(paper_uuid))
        if os.path.exists(json_path):
            os.remove(json_path)
    except Exception:
        pass

    # Remove DB row
    db.delete(row)
    db.flush()

    # Tombstone slugs
    try:
        slug_rows = db.query(PaperSlugRow).filter(PaperSlugRow.paper_uuid == str(paper_uuid)).all()
        now = datetime.utcnow()
        for s in slug_rows:
            s.paper_uuid = None
            s.tombstone = True
            s.deleted_at = now
            db.add(s)
    except Exception:
        # best-effort
        pass

    db.commit()
    return True


