from __future__ import annotations

from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Page:
    """Simple page model for papers."""
    page_number: int
    img_base64: str


@dataclass 
class Section:
    """Simple section model for papers."""
    order_index: int
    rewritten_content: str


@dataclass
class PaperSlug:
    """Paper slug DTO."""
    slug: str
    paper_uuid: Optional[str] = None
    created_at: Optional[datetime] = None
    tombstone: bool = False
    deleted_at: Optional[datetime] = None


@dataclass
class Paper:
    """
    Complete Paper DTO containing both metadata and full processing results.
    
    For metadata-only operations, content fields (pages, sections) will be empty.
    For full paper operations, all fields are populated from database + JSON.
    """
    # Database metadata fields
    paper_uuid: str
    arxiv_id: str
    title: Optional[str] = None
    authors: Optional[str] = None
    status: str = "not_started"
    arxiv_version: Optional[str] = None
    arxiv_url: Optional[str] = None
    error_message: Optional[str] = None
    initiated_by_user_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    num_pages: Optional[int] = None
    processing_time_seconds: Optional[float] = None
    total_cost: Optional[float] = None
    avg_cost_per_page: Optional[float] = None
    thumbnail_data_url: Optional[str] = None
    
    # Full processing content fields (loaded from JSON when needed)
    pages: List[Page] = field(default_factory=list)
    sections: List[Section] = field(default_factory=list)



