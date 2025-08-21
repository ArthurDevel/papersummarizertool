from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel


class SearchQueryRequest(BaseModel):
    query: str
    is_new: bool = False
    selected_categories: Optional[List[str]] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    limit: int = 20


class SearchItem(BaseModel):
    paper_uuid: str
    slug: Optional[str] = None
    title: Optional[str] = None
    authors: Optional[str] = None
    published: Optional[str] = None
    abs_url: Optional[str] = None
    summary: Optional[str] = None
    qdrant_score: Optional[float] = None
    rerank_score: Optional[float] = None


class SearchQueryResponse(BaseModel):
    items: List[SearchItem]
    rewritten_query: Optional[str] = None
    applied_categories: Optional[List[str]] = None
    applied_date_from: Optional[str] = None
    applied_date_to: Optional[str] = None


class SimilarPapersResponse(BaseModel):
    items: List[SearchItem]


