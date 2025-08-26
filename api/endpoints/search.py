from __future__ import annotations

from typing import List
import json
import logging

from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy.orm import Session

from api.types.search import (
    SearchQueryRequest,
    SearchQueryResponse,
    SearchItem,
    SimilarPapersResponse,
)
from search.client import search_by_user_query, find_similar_papers
from shared.arxiv.client import _split_id_and_version
from shared.db import get_session
from papers.models import PaperSlugRow, PaperRow


router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/search/query", response_model=SearchQueryResponse)
async def search_query(req: SearchQueryRequest, db: Session = Depends(get_session)) -> SearchQueryResponse:
    results, meta = await search_by_user_query(
        query=req.query,
        is_new=req.is_new,
        selected_categories=req.selected_categories,
        date_from=req.date_from,
        date_to=req.date_to,
        limit=max(1, min(req.limit or 20, 100)),
        rerank_top_k=max(1, min((req.limit or 20) * 3, 200)),
    )

    # Step 1: Extract arxiv_id from each search result's payload.
    result_arxiv_ids = []
    for r in results:
        payload = r.get("point", {}).get("payload", {})
        abs_url = payload.get("abs_url", "")
        arxiv_id = None
        if '/abs/' in abs_url:
            try:
                arxiv_id, _ = _split_id_and_version(abs_url.split('/abs/')[-1])
            except Exception:
                pass
        result_arxiv_ids.append(arxiv_id)
    
    logger.info(f"Extracted {len([i for i in result_arxiv_ids if i])} arxiv_ids from search results.")

    # Step 2: Query the DB to find which of these papers we have processed.
    db_papers_by_arxiv_id = {}
    if result_arxiv_ids:
        paper_rows = db.query(PaperRow).filter(PaperRow.arxiv_id.in_(result_arxiv_ids)).all()
        db_papers_by_arxiv_id = {p.arxiv_id: p for p in paper_rows}
        logger.info(f"Found {len(paper_rows)} matching papers in the database.")

    # Step 3: Find the latest slugs for the papers we found in our DB.
    db_slugs_by_paper_uuid = {}
    paper_uuids_from_db = [p.paper_uuid for p in db_papers_by_arxiv_id.values()]
    if paper_uuids_from_db:
        slug_rows = (
            db.query(PaperSlugRow)
            .filter(PaperSlugRow.paper_uuid.in_(paper_uuids_from_db))
            .filter(PaperSlugRow.tombstone == False)
            .all()
        )
        for row in slug_rows:
            puid = row.paper_uuid
            if puid not in db_slugs_by_paper_uuid or row.created_at > db_slugs_by_paper_uuid[puid]["created_at"]:
                db_slugs_by_paper_uuid[puid] = {"slug": row.slug, "created_at": row.created_at}
        logger.info(f"Found slugs for {len(db_slugs_by_paper_uuid)} papers.")

    # Step 4: Build the final response items, enriching with DB data.
    items: List[SearchItem] = []
    for i, r in enumerate(results):
        point = (r or {}).get("point") or {}
        payload = (point or {}).get("payload") or {}
        
        arxiv_id = result_arxiv_ids[i]
        paper_in_db = db_papers_by_arxiv_id.get(arxiv_id) if arxiv_id else None
        
        paper_uuid = ""
        slug = None

        if paper_in_db:
            paper_uuid = paper_in_db.paper_uuid
            slug_info = db_slugs_by_paper_uuid.get(paper_uuid)
            if slug_info:
                slug = slug_info["slug"]
        else:
            # Fallback to payload info if not in DB
            paper_uuid = str(payload.get("paper_uuid") or point.get("id") or "")
            slug = payload.get("slug")

        if not slug:
            logger.warning(f"Slug for paper with arxiv_id {arxiv_id} is null. DB paper found: {bool(paper_in_db)}. Qdrant point id was {point.get('id')}.")

        authors_val = ", ".join(json.loads(payload.get("authors_json") or "[]"))
        items.append(
            SearchItem(
                paper_uuid=paper_uuid,
                slug=slug,
                title=payload.get("title"),
                authors=authors_val,
                published=payload.get("published"),
                abs_url=payload.get("abs_url"),
                summary=payload.get("summary"),
                qdrant_score=r.get("qdrant_score"),
                rerank_score=r.get("rerank_score"),
            )
        )
        
    try:
        logger.info(
            "Search /search/query returning items=%s rewritten=%s cats=%s dates=%s→%s",
            len(items),
            bool(meta.get("rewritten_query")),
            (meta.get("applied_categories") or [])[:5],
            meta.get("applied_date_from"),
            meta.get("applied_date_to"),
        )
    except Exception:
        pass
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
        # Authors strictly from authors_json (JSON string)
        authors_val = ", ".join(json.loads(payload.get("authors_json") or "[]"))
        try:
            logger.info(
                "Similar map item: id=%s title=%s authors_json_len=%s abs_url=%s",
                str((point or {}).get("id")),
                (payload.get("title") or '')[:80],
                len(payload.get("authors_json") or []),
                payload.get("abs_url"),
            )
            raw_authors_json = payload.get("authors_json")
            logger.info(
                "Similar authors debug: id=%s authors_json_type=%s authors_json_len=%s authors_str_preview=%s",
                str((point or {}).get("id")),
                type(raw_authors_json).__name__,
                (len(raw_authors_json) if isinstance(raw_authors_json, list) else None),
                (authors_val or '')[:100],
            )
            try:
                raw_preview = str(raw_authors_json)
            except Exception:
                raw_preview = "<unprintable>"
            logger.info(
                "Similar authors raw: id=%s raw=%s",
                str((point or {}).get("id")),
                (raw_preview[:500] if isinstance(raw_preview, str) else raw_preview),
            )
        except Exception:
            pass
        items.append(
            SearchItem(
                paper_uuid=str((point or {}).get("id") or payload.get("paper_uuid") or ""),
                slug=payload.get("slug"),
                title=payload.get("title"),
                authors=authors_val,
                published=payload.get("published"),
                abs_url=payload.get("abs_url"),
                summary=payload.get("summary"),
                qdrant_score=r.get("qdrant_score"),
                rerank_score=None,
            )
        )
    return SimilarPapersResponse(items=items)


