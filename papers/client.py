from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from typing import Any, Dict, List, Optional
import hashlib
import json as _json
import os
import re
import unicodedata
import uuid

from sqlalchemy.orm import Session

from papers.models import Paper, PaperSlug, Page, Section
from papers.db.client import (
    get_paper_record, create_paper_record, update_paper_record, list_paper_records, 
    get_paper_slugs, get_all_paper_slugs, tombstone_paper_slugs,
    find_existing_paper_slug_record, find_slug_record_by_name, create_paper_slug_record
)
from papers.db.models import PaperRecord
from paperprocessor.models import ProcessedDocument


### HELPER FUNCTIONS ###

def get_processed_result_path(paper_uuid: str) -> str:
    """
    Return absolute filesystem path for the stored processed result JSON for a paper.
    Directory is controlled by env PAPER_JSON_DIR (default: data/paperjsons/).
    """
    base_dir = os.path.abspath(os.environ.get("PAPER_JSON_DIR", os.path.join(os.getcwd(), 'data', 'paperjsons')))
    return os.path.join(base_dir, f"{paper_uuid}.json")


def build_paper_slug(title: Optional[str], authors: Optional[str]) -> str:
    """
    Generate a URL-safe slug from paper title and authors.
    
    Args:
        title: Paper title
        authors: Comma-separated author names
        
    Returns:
        str: URL-safe slug (max 120 characters)
        
    Raises:
        ValueError: If title or authors are missing
    """
    if not title or not authors:
        raise ValueError("Cannot generate slug without title and authors")
    
    # Step 1: Normalize unicode characters to ASCII
    try:
        normalized_title = unicodedata.normalize('NFKD', title).encode('ascii', 'ignore').decode('ascii')
        normalized_authors = unicodedata.normalize('NFKD', authors).encode('ascii', 'ignore').decode('ascii')
    except Exception:
        normalized_title, normalized_authors = title, authors
    
    # Step 2: Extract first 12 words from title
    title_words = [word for word in normalized_title.split() if word][:12]
    title_part = " ".join(title_words) if title_words else normalized_title
    
    # Step 3: Extract up to 2 author last names
    author_names = [name.strip() for name in normalized_authors.split(',') if name.strip()]
    if not author_names:
        raise ValueError("Cannot generate slug: no authors present")
    
    def _extract_last_name(full_name: str) -> str:
        name_parts = full_name.split()
        return name_parts[-1] if name_parts else full_name
    
    author_last_names = [_extract_last_name(name) for name in author_names[:2]]
    author_part = " ".join(author_last_names)
    
    # Step 4: Combine and create URL-safe slug
    combined_text = f"{title_part} {author_part}".strip()
    slug = combined_text.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip('-')
    
    return slug[:120]


def find_existing_paper_slug(db: Session, paper_uuid: str) -> Optional[PaperSlug]:
    """
    Find existing non-tombstoned slug for a paper.
    
    Args:
        db: Active database session
        paper_uuid: UUID of the paper to find slug for
        
    Returns:
        Optional[PaperSlug]: Existing slug DTO if found, None otherwise
    """
    existing_slug_record = find_existing_paper_slug_record(db, paper_uuid)
    if existing_slug_record:
        return PaperSlug.model_validate(existing_slug_record)
    return None


def create_paper_slug(db: Session, paper: Paper) -> PaperSlug:
    """
    Create a unique slug for a paper, checking for collisions.
    
    Args:
        db: Active database session
        paper: Paper object with title and authors
        
    Returns:
        PaperSlug: Created or existing slug DTO
        
    Raises:
        ValueError: If slug collision occurs with different paper
    """
    # Step 1: Check if paper already has a slug
    existing_slug = find_existing_paper_slug(db, paper.paper_uuid)
    if existing_slug:
        return existing_slug
    
    # Step 2: Generate new slug from paper metadata
    new_slug_string = build_paper_slug(paper.title, paper.authors)
    
    # Step 3: Check for slug collisions
    existing_slug_record = find_slug_record_by_name(db, new_slug_string)
    
    if existing_slug_record:
        # Allow reuse if slug already maps to this same paper
        if existing_slug_record.paper_uuid != paper.paper_uuid:
            raise ValueError(f"Slug collision for '{new_slug_string}' - already used by different paper")
        return PaperSlug.model_validate(existing_slug_record)
    
    # Step 4: Create new slug record using database layer
    created_slug_record = create_paper_slug_record(db, new_slug_string, paper.paper_uuid)
    
    return PaperSlug.model_validate(created_slug_record)


### MAIN FUNCTIONS ###

def list_papers(db: Session, statuses: Optional[List[str]], limit: int) -> List[Paper]:
    records = list_paper_records(db, statuses, limit)
    return [Paper.model_validate(record) for record in records]


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
    slug_records = get_all_paper_slugs(db, non_tombstone_only=True)
    slug_dtos = [PaperSlug.model_validate(record) for record in slug_records]
    latest_by_uuid: Dict[str, Dict[str, Any]] = {}
    for slug_dto in slug_dtos:
        puid = slug_dto.paper_uuid
        if not puid:
            continue
        current = latest_by_uuid.get(puid)
        if current is None or (slug_dto.created_at and current.get("created_at") and slug_dto.created_at > current["created_at"]):
            latest_by_uuid[puid] = {"slug": slug_dto.slug, "created_at": slug_dto.created_at}

    for it in items:
        m = latest_by_uuid.get(it["paper_uuid"]) if isinstance(it, dict) else None
        if m:
            it["slug"] = m["slug"]

    return items


def delete_paper(db: Session, paper_uuid: str) -> bool:
    row = get_paper_record(db, str(paper_uuid))
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
        tombstone_paper_slugs(db, str(paper_uuid))
    except Exception:
        # best-effort
        pass

    db.commit()
    return True


def save_paper(db: Session, processed_content: ProcessedDocument) -> Paper:
    """
    Save processed document to database and JSON file.
    
    Args:
        db: Database session
        processed_content: ProcessedDocument with full processing results
        
    Returns:
        Paper: Created or updated Paper object
        
    Raises:
        ValueError: If creating new paper but arxiv_id already exists
        RuntimeError: If missing required fields
    """
    if not processed_content.arxiv_id:
        raise RuntimeError("ProcessedDocument must have arxiv_id")
    
    # Step 1: Determine if this is create or update
    if processed_content.paper_uuid:
        # Update existing paper
        paper_uuid = processed_content.paper_uuid
        arxiv_id = processed_content.arxiv_id
        is_update = True
    else:
        # Create new paper - check for duplicates first
        existing_paper = get_paper_record(db, processed_content.arxiv_id, by_arxiv_id=True)
        if existing_paper:
            raise ValueError(f"Paper with arXiv ID {processed_content.arxiv_id} already exists")
        
        paper_uuid = str(uuid.uuid4())
        arxiv_id = processed_content.arxiv_id
        is_update = False
    
    # Step 2: Convert ProcessedDocument to legacy JSON format
    result_dict = {
        "paper_id": paper_uuid,
        "title": processed_content.title,
        "authors": processed_content.authors,
        "thumbnail_data_url": None,  # Will be set from first page
        "sections": [],
        "tables": [],
        "figures": [],
        "pages": [],
        "usage_summary": {},
        "processing_time_seconds": 0.0,
        "num_pages": len(processed_content.pages),
        "total_cost": 0.0,
        "avg_cost_per_page": 0.0,
    }
    
    # Convert pages to legacy format
    for idx, page in enumerate(processed_content.pages):
        result_dict["pages"].append({
            "page_number": idx + 1,
            "image_data_url": f"data:image/png;base64,{page.img_base64}",
        })
    
    # Convert individual images from pages to legacy figures format
    for page in processed_content.pages:
        for processed_image in page.images:
            result_dict["figures"].append({
                "figure_identifier": processed_image.uuid,
                "location_page": processed_image.page_number,
                "explanation": "",  # Not extracted in current pipeline
                "image_path": "",   # Not used - we store base64 directly
                "image_data_url": f"data:image/png;base64,{processed_image.img_base64}",
                "referenced_on_pages": [processed_image.page_number],
                "bounding_box": [
                    processed_image.top_left_x,
                    processed_image.top_left_y,
                    processed_image.bottom_right_x,
                    processed_image.bottom_right_y
                ],
                # TODO: Add page dimensions to ProcessedPage model to get actual size
                "page_image_size": None  # Unknown - not stored in ProcessedPage
            })
    
    # Set thumbnail from first page
    if processed_content.pages:
        result_dict["thumbnail_data_url"] = f"data:image/png;base64,{processed_content.pages[0].img_base64}"
    
    # Convert sections to legacy format
    for section in processed_content.sections:
        result_dict["sections"].append({
            "rewritten_content": section.rewritten_content,
        })
    
    # Calculate usage summary and costs
    from paperprocessor.client import _calculate_usage_summary
    usage_summary = _calculate_usage_summary(processed_content.step_costs)
    result_dict["usage_summary"] = usage_summary
    result_dict["total_cost"] = usage_summary.get("total_cost")
    if result_dict["total_cost"] and result_dict["num_pages"] > 0:
        result_dict["avg_cost_per_page"] = result_dict["total_cost"] / result_dict["num_pages"]
    
    # Step 3: Save JSON file
    json_path = get_processed_result_path(paper_uuid)
    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    tmp_path = f"{json_path}.tmp"
    with open(tmp_path, 'w', encoding='utf-8') as f:
        _json.dump(result_dict, f, ensure_ascii=False)
    os.replace(tmp_path, json_path)
    
    # Step 4: Create or update paper record in database
    paper_data = {
        'paper_uuid': paper_uuid,
        'arxiv_id': arxiv_id,
        'title': processed_content.title,
        'authors': processed_content.authors,
        'status': 'completed',
        'num_pages': len(processed_content.pages),
        'total_cost': result_dict["total_cost"],
        'avg_cost_per_page': result_dict["avg_cost_per_page"],
        'thumbnail_data_url': result_dict["thumbnail_data_url"],
        'finished_at': datetime.utcnow(),
    }
    
    if is_update:
        record = update_paper_record(db, paper_uuid, paper_data)
    else:
        record = create_paper_record(db, paper_data)
    
    return Paper.model_validate(record)


def get_paper_metadata(db: Session, paper_uuid: str) -> Paper:
    """
    Get paper metadata from database only.
    
    Returns:
        Paper: Database record with metadata fields only
        
    Raises:
        FileNotFoundError: If paper with UUID not found
    """
    record = get_paper_record(db, paper_uuid)
    return Paper.model_validate(record)


def get_paper(db: Session, paper_uuid: str) -> Paper:
    """
    Get complete paper by UUID.
    Loads both database metadata and full processing results from JSON file.
    
    Returns:
        Paper: Complete paper with metadata and content (pages, sections)
        
    Raises:
        FileNotFoundError: If paper with UUID not found or JSON file missing
    """
    # Step 1: Get database metadata
    paper = get_paper_metadata(db, paper_uuid)
    
    # Step 2: Load JSON file with full processing results
    json_path = get_processed_result_path(paper_uuid)
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"Processed result JSON not found for paper {paper_uuid}")
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            result_dict = _json.load(f)
    except Exception as e:
        raise RuntimeError(f"Failed to load processed result JSON for paper {paper_uuid}: {e}")
    
    # Step 3: Convert legacy JSON format to our DTOs
    
    # Convert pages from legacy format
    pages = []
    for page_data in result_dict.get("pages", []):
        # Extract base64 from data URL
        image_data_url = page_data.get("image_data_url", "")
        if image_data_url.startswith("data:image/png;base64,"):
            img_base64 = image_data_url[len("data:image/png;base64,"):]
        else:
            img_base64 = ""
        
        page = Page(
            page_number=page_data.get("page_number", 0),
            img_base64=img_base64
        )
        pages.append(page)
    
    # Convert sections from legacy format
    sections = []
    for idx, section_data in enumerate(result_dict.get("sections", [])):
        section = Section(
            order_index=idx,
            rewritten_content=section_data.get("rewritten_content", "")
        )
        sections.append(section)
    
    # Step 4: Add content to paper DTO
    paper.pages = pages
    paper.sections = sections
    
    return paper


