from __future__ import annotations

from typing import List, Optional, Dict, Any

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchAny, MatchValue, Range

from shared.config import settings
from shared.qdrant.models import VectorPoint


# Domain-agnostic default; callers should pass an explicit collection
_COLLECTION_NAME = "vectors"


def _client() -> QdrantClient:
    return QdrantClient(
        host=settings.QDRANT_HOST,
        port=settings.QDRANT_PORT,
        api_key=(settings.QDRANT_API_KEY or None),
        https=False,
    )


def ensure_collection(vector_size: int, collection: str = _COLLECTION_NAME) -> None:
    client = _client()
    existing = client.get_collections()
    names = {c.name for c in (existing.collections or [])}
    if collection in names:
        return
    client.recreate_collection(
        collection_name=collection,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )


def upsert_point(
    point_id: str,
    vector: List[float],
    payload: Dict[str, Any],
    collection: str = _COLLECTION_NAME,
) -> None:
    client = _client()
    point = PointStruct(
        id=point_id,
        vector=vector,
        payload={k: v for k, v in (payload or {}).items() if v is not None},
    )
    client.upsert(collection_name=collection, points=[point])


def _build_filter(
    categories: Optional[List[str]] = None,
    date_from_ts: Optional[int] = None,
    date_to_ts: Optional[int] = None,
) -> Optional[Filter]:
    conditions: List[Any] = []
    if categories:
        conditions.append(
            FieldCondition(key="categories", match=MatchAny(any=categories))
        )
    if date_from_ts is not None:
        conditions.append(FieldCondition(key="published_at_ts", range=Range(gte=date_from_ts)))
    if date_to_ts is not None:
        conditions.append(FieldCondition(key="published_at_ts", range=Range(lte=date_to_ts)))
    if not conditions:
        return None
    return Filter(must=conditions)


def search_by_vector(
    query_vector: List[float],
    limit: int = 50,
    categories: Optional[List[str]] = None,
    date_from_ts: Optional[int] = None,
    date_to_ts: Optional[int] = None,
    collection: str = _COLLECTION_NAME,
) -> List[VectorPoint]:
    client = _client()
    flt = _build_filter(categories=categories, date_from_ts=date_from_ts, date_to_ts=date_to_ts)
    res = client.search(
        collection_name=collection,
        query_vector=query_vector,
        limit=max(1, limit),
        query_filter=flt,
        with_payload=True,
        with_vectors=False,
    )
    # Normalize into a generic list of dicts with payload and score
    out: List[VectorPoint] = []
    for p in res:
        out.append(VectorPoint(id=str(p.id), score=float(p.score) if p.score is not None else None, payload=p.payload or {}))
    return out


def get_vector_by_id(point_id: str, collection: str = _COLLECTION_NAME) -> Optional[List[float]]:
    client = _client()
    recs = client.retrieve(collection_name=collection, ids=[point_id], with_vectors=True, with_payload=False)
    if not recs:
        return None
    vec = getattr(recs[0], "vector", None)
    return list(vec) if isinstance(vec, list) else vec


