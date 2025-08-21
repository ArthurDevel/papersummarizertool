from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException, status

from api.types.search import (
    SearchQueryRequest,
    SearchQueryResponse,
    SearchItem,
    SimilarPapersResponse,
)
from shared.arxiv.client import search_by_user_query, find_similar_papers


router = APIRouter()


@router.post("/search/query", response_model=SearchQueryResponse)
async def search_query(req: SearchQueryRequest) -> SearchQueryResponse:
    results, meta = await search_by_user_query(
        query=req.query,
        is_new=req.is_new,
        selected_categories=req.selected_categories,
        date_from=req.date_from,
        date_to=req.date_to,
        limit=max(1, min(req.limit or 20, 100)),
        rerank_top_k=max(1, min((req.limit or 20) * 3, 200)),
    )
    items: List[SearchItem] = []
    for r in results:
        point = (r or {}).get("point") or {}
        payload = (point or {}).get("payload") or {}
        items.append(
            SearchItem(
                paper_uuid=str((point or {}).get("id") or payload.get("paper_uuid") or ""),
                slug=payload.get("slug"),
                title=payload.get("title"),
                authors=payload.get("authors"),
                qdrant_score=r.get("qdrant_score"),
                rerank_score=r.get("rerank_score"),
            )
        )
    return SearchQueryResponse(
        items=items,
        rewritten_query=meta.get("rewritten_query"),
        applied_categories=meta.get("applied_categories"),
        applied_date_from=meta.get("applied_date_from"),
        applied_date_to=meta.get("applied_date_to"),
    )


@router.get("/search/paper/{paper_uuid}/similar", response_model=SimilarPapersResponse)
async def similar_papers(paper_uuid: str, limit: int = 20) -> SimilarPapersResponse:
    if not paper_uuid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="paper_uuid is required")
    results = await find_similar_papers(paper_uuid=paper_uuid, limit=max(1, min(limit, 100)))
    items: List[SearchItem] = []
    for r in results:
        point = (r or {}).get("point") or {}
        payload = (point or {}).get("payload") or {}
        items.append(
            SearchItem(
                paper_uuid=str((point or {}).get("id") or payload.get("paper_uuid") or ""),
                slug=payload.get("slug"),
                title=payload.get("title"),
                authors=payload.get("authors"),
                qdrant_score=r.get("qdrant_score"),
                rerank_score=None,
            )
        )
    return SimilarPapersResponse(items=items)


