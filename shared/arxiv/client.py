import re
import httpx
from typing import Optional, Tuple, List, Union, Dict, Any
from datetime import datetime
import logging
import email.utils
import xml.etree.ElementTree as ET

from shared.arxiv.models import (
    ParsedArxivUrl,
    NormalizedArxivId,
    ArxivMetadata,
    ArxivAuthor,
    ArxivVersion,
    ArxivPdfHead,
    ArxivPdfResult,
    ArxivPdfForProcessing,
)
from shared.qdrant.client import search_by_vector as qdrant_search_by_vector, get_vector_by_id as qdrant_get_vector_by_id, ensure_collection as qdrant_ensure_collection
from shared.voyageai.client import embed_query as voyage_embed_query, rerank as voyage_rerank
from shared.openrouter.client import get_json_response as or_get_json_response, get_llm_response as or_get_llm_response
from shared.arxiv.internals.prompt_loader import load_prompt as load_arxiv_prompt
from shared.utils import to_epoch_seconds
import os


logger = logging.getLogger(__name__)

# Endpoints and networking defaults
ARXIV_HOST = "https://arxiv.org"
ARXIV_EXPORT_HOST = "http://export.arxiv.org"
TIMEOUT_SECONDS = 60
DEFAULT_HEADERS = {
    "User-Agent": "papersummarizer/0.1 (+https://arxiv.org)",
}


# --- Helpers: ID parsing / normalization ---

_NEW_STYLE_RE = re.compile(r"^(?P<id>\d{4}\.\d{4,5})(?P<ver>v\d+)?$")
_OLD_STYLE_RE = re.compile(r"^(?P<id>[a-z\-]+(?:\.[A-Z]{2})?/\d{7})(?P<ver>v\d+)?$", re.IGNORECASE)


def _split_id_and_version(id_or_versioned: str) -> Tuple[str, Optional[str]]:
    m = _NEW_STYLE_RE.match(id_or_versioned)
    if m:
        return m.group("id"), m.group("ver")
    m = _OLD_STYLE_RE.match(id_or_versioned)
    if m:
        return m.group("id"), m.group("ver")
    # If user passed something like 1234.56789v2.pdf or with .pdf suffix, strip it and retry
    cleaned = id_or_versioned.strip()
    if cleaned.endswith(".pdf"):
        cleaned = cleaned[:-4]
    if cleaned.lower().startswith("arxiv:"):
        cleaned = cleaned.split(":", 1)[1]
    # One more attempt after cleaning
    m = _NEW_STYLE_RE.match(cleaned) or _OLD_STYLE_RE.match(cleaned)
    if m:
        return m.group("id"), m.group("ver")
    raise ValueError(f"Unrecognized arXiv identifier: {id_or_versioned}")


async def parse_url(url: str) -> ParsedArxivUrl:
    """Parse an arXiv URL or identifier into components."""
    raw = url.strip()
    # Accept raw IDs / arXiv:ID
    if not raw.startswith("http://") and not raw.startswith("https://"):
        arxiv_id, version = _split_id_and_version(raw)
        return ParsedArxivUrl(raw=raw, arxiv_id=arxiv_id, version=version, url_type="id")

    # Normalize hostname and path
    m = re.match(r"^https?://[^/]+/(.+)$", raw)
    if not m:
        raise ValueError("Invalid arXiv URL")
    path = m.group(1)

    # Match /abs/<id>(vN)[optional slash] with optional query/fragment
    abs_m = re.match(r"^abs/(?P<idver>[^/?#]+)(?:/)?(?:[?#].*)?$", path)
    if abs_m:
        idver = abs_m.group("idver")
        arxiv_id, version = _split_id_and_version(idver)
        return ParsedArxivUrl(raw=raw, arxiv_id=arxiv_id, version=version, url_type="abs")

    # Match /pdf/<id>(vN)[.pdf optional][optional slash] with optional query/fragment
    pdf_m = re.match(r"^pdf/(?P<idver>[^/?#]+?)(?:\.pdf)?(?:/)?(?:[?#].*)?$", path)
    if pdf_m:
        idver = pdf_m.group("idver")
        arxiv_id, version = _split_id_and_version(idver)
        return ParsedArxivUrl(raw=raw, arxiv_id=arxiv_id, version=version, url_type="pdf")

    raise ValueError("Unsupported arXiv URL format")


async def normalize_id(id_or_url: str) -> NormalizedArxivId:
    """Return canonical arXiv id and optional version from a URL or ID string."""
    try:
        parsed = await parse_url(id_or_url)
        return NormalizedArxivId(arxiv_id=parsed.arxiv_id, version=parsed.version)
    except ValueError:
        arxiv_id, version = _split_id_and_version(id_or_url)
        return NormalizedArxivId(arxiv_id=arxiv_id, version=version)


def build_pdf_url(arxiv_id: str, version: Optional[str] = None) -> str:
    suffix = version or ""
    return f"{ARXIV_HOST}/pdf/{arxiv_id}{suffix}.pdf"


def _http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=TIMEOUT_SECONDS, follow_redirects=True)


def _parse_rfc2822_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        ts = email.utils.parsedate_to_datetime(value)
        return ts
    except Exception:
        return None


def _find_text(elem: ET.Element, tag: str) -> Optional[str]:
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "arxiv": "http://arxiv.org/schemas/atom",
    }
    found = elem.find(tag, ns)
    return found.text.strip() if found is not None and found.text else None


async def fetch_metadata(arxiv_id: str) -> ArxivMetadata:
    """Fetch metadata from arXiv Atom API for a single identifier."""
    query_url = f"{ARXIV_EXPORT_HOST}/api/query?id_list={arxiv_id}"
    async with _http_client() as client:
        resp = await client.get(query_url)
        resp.raise_for_status()
        content = resp.content

    # Parse Atom XML
    root = ET.fromstring(content)
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "arxiv": "http://arxiv.org/schemas/atom",
    }
    entry = root.find("atom:entry", ns)
    if entry is None:
        raise ValueError(f"No metadata found for {arxiv_id}")

    title = _find_text(entry, "atom:title") or ""
    summary = _find_text(entry, "atom:summary") or ""
    doi = _find_text(entry, "arxiv:doi")
    journal_ref = _find_text(entry, "arxiv:journal_ref")
    updated_str = _find_text(entry, "atom:updated")
    published_str = _find_text(entry, "atom:published")

    # Authors
    authors: List[ArxivAuthor] = []
    for a in entry.findall("atom:author", ns):
        name = _find_text(a, "atom:name") or ""
        affiliation = _find_text(a, "arxiv:affiliation")
        authors.append(ArxivAuthor(name=name, affiliation=affiliation))

    # Categories
    categories = [c.attrib.get("term", "") for c in entry.findall("atom:category", ns) if c.attrib.get("term")]

    # Versions
    versions: List[ArxivVersion] = []
    for v in entry.findall("arxiv:version", ns):
        ver = v.attrib.get("version") or (v.text.strip() if v.text else None)
        dt = _parse_rfc2822_date(v.attrib.get("updated")) or _parse_rfc2822_date(v.text)
        if ver:
            versions.append(ArxivVersion(version=ver, updated_at=dt))

    latest_version = versions[-1].version if versions else None

    return ArxivMetadata(
        arxiv_id=arxiv_id,
        latest_version=latest_version,
        title=title,
        authors=authors,
        summary=summary,
        categories=categories,
        doi=doi,
        journal_ref=journal_ref,
        submitted_at=_parse_rfc2822_date(published_str),
        updated_at=_parse_rfc2822_date(updated_str),
        all_versions=versions,
    )


async def head_pdf(arxiv_id: str, version: Optional[str] = None) -> ArxivPdfHead:
    url = build_pdf_url(arxiv_id, version)
    async with _http_client() as client:
        resp = await client.head(url)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type")
        content_length = resp.headers.get("Content-Length")
        try:
            cl_int = int(content_length) if content_length is not None else None
        except ValueError:
            cl_int = None
        cd = resp.headers.get("Content-Disposition")
        filename: Optional[str] = None
        if cd and "filename=" in cd:
            filename = cd.split("filename=", 1)[1].strip().strip('"')
        if not filename:
            suffix = (version or "")
            filename = f"{arxiv_id}{suffix}.pdf"
        return ArxivPdfHead(url=url, filename=filename, content_type=content_type, content_length=cl_int)


async def download_pdf(arxiv_id: str, version: Optional[str] = None) -> ArxivPdfResult:
    url = build_pdf_url(arxiv_id, version)
    async with _http_client() as client:
        resp = await client.get(url)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type") or "application/pdf"
        content_length = resp.headers.get("Content-Length")
        try:
            cl_int = int(content_length) if content_length is not None else None
        except ValueError:
            cl_int = None
        cd = resp.headers.get("Content-Disposition")
        filename: Optional[str] = None
        if cd and "filename=" in cd:
            filename = cd.split("filename=", 1)[1].strip().strip('"')
        if not filename:
            suffix = (version or "")
            filename = f"{arxiv_id}{suffix}.pdf"
        pdf_bytes = resp.content
        return ArxivPdfResult(url=str(resp.url), filename=filename, content_type=content_type, content_length=cl_int, pdf_bytes=pdf_bytes)


async def download_pdf_by_url(url: str) -> ArxivPdfResult:
    parsed = await parse_url(url)
    return await download_pdf(parsed.arxiv_id, parsed.version)


async def fetch_pdf_for_processing(id_or_url: str) -> ArxivPdfForProcessing:
    norm = await normalize_id(id_or_url)
    # If version unspecified, prefer latest metadata version
    version = norm.version
    metadata: Optional[ArxivMetadata] = None
    try:
        metadata = await fetch_metadata(norm.arxiv_id)
        if version is None and metadata.latest_version:
            version = metadata.latest_version
    except Exception as e:
        logger.warning("Failed to fetch arXiv metadata for %s: %s", norm.arxiv_id, e)
    pdf = await download_pdf(norm.arxiv_id, version)
    return ArxivPdfForProcessing(pdf_bytes=pdf.pdf_bytes, filename=pdf.filename, metadata=metadata)


# Intentionally no classes; functional, stateless helpers only



# --- Simple search helpers ---

async def search_metadata_by_title(title_query: str) -> Optional[ArxivMetadata]:
    """Search arXiv by exact title phrase and return the first match's metadata, if any.

    This uses the export.arxiv.org ATOM API with a title phrase query.
    """
    if not title_query or not title_query.strip():
        return None
    q = title_query.strip().replace('\n', ' ').strip()
    # Use quoted phrase match; limit to a few results
    search_url = f"{ARXIV_EXPORT_HOST}/api/query?search_query=ti:\"{httpx.QueryParams({'q': q}).get('q')}\"&start=0&max_results=3"
    async with _http_client() as client:
        try:
            resp = await client.get(search_url)
            resp.raise_for_status()
        except Exception:
            logger.exception("arXiv title search failed")
            return None
        content = resp.content
    try:
        root = ET.fromstring(content)
        ns = {
            "atom": "http://www.w3.org/2005/Atom",
            "arxiv": "http://arxiv.org/schemas/atom",
        }
        entry = root.find("atom:entry", ns)
        if entry is None:
            return None
        # Extract id like http://arxiv.org/abs/XXXX
        id_text = (entry.find("atom:id", ns).text or "").strip()
        m = re.search(r"/(?:abs|pdf)/([^/]+)", id_text)
        if not m:
            # Fallback: try title-only parse
            title = _find_text(entry, "atom:title") or ""
            # Without an id, we can still return a partial metadata; but we prefer full
            return ArxivMetadata(
                arxiv_id="",
                latest_version=None,
                title=title,
                authors=[],
                abstract=_find_text(entry, "atom:summary") or "",
                categories=[],
                doi=None,
                journal_ref=None,
                submitted_at=None,
                updated_at=None,
                all_versions=[],
            )
        idver = m.group(1)
        base_id = _split_id_and_version(idver)[0]
        return await fetch_metadata(base_id)
    except Exception:
        logger.exception("Failed to parse arXiv title search response")
        return None


# --- Vector search orchestration (user query and similar papers) ---

from functools import lru_cache


@lru_cache(maxsize=1)
def _read_arxiv_categories() -> List[str]:
    """Load arXiv categories list from CSV into a flat list of terms."""
    try:
        base_dir = os.path.abspath(os.path.join(os.getcwd(), 'shared', 'arxiv', 'internals'))
        path = os.path.join(base_dir, 'arxiv_categories.csv')
        items: List[str] = []
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = (line or '').strip()
                if not line or line.lower().startswith('category'):
                    # Skip header or empty
                    continue
                parts = [p.strip() for p in line.split(',')]
                if parts:
                    items.append(parts[0])
        return items
    except Exception:
        logger.exception("Failed to read arXiv categories CSV")
        return []


_to_epoch_seconds = to_epoch_seconds


async def search_by_user_query(
    query: str,
    is_new: bool = False,
    selected_categories: Optional[List[str]] = None,
    date_from: Optional[Union[str, datetime]] = None,
    date_to: Optional[Union[str, datetime]] = None,
    limit: int = 20,
    rerank_top_k: int = 50,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Orchestrate user search across VoyageAI + Qdrant with optional LLM-assisted filters.
    Returns (results, meta).
    results: list of { point, qdrant_score, rerank_score }
    meta: { rewritten_query?, applied_categories?, applied_date_from?, applied_date_to? }
    """
    original_query = (query or '').strip()
    if not original_query:
        return [], {"error": "empty_query"}

    applied_categories: Optional[List[str]] = selected_categories[:] if selected_categories else None
    applied_date_from = date_from
    applied_date_to = date_to
    rewritten_query: Optional[str] = None

    # Step A: If is_new, ask LLM for categories/date range and a rewritten query
    if is_new and not selected_categories and not (date_from or date_to):
        try:
            cats = _read_arxiv_categories()
            # Load prompts
            rewrite_sys = load_arxiv_prompt('search_rewrite_system.md')
            # cats_sys = load_arxiv_prompt('search_select_categories_system.md')
            # dates_sys = load_arxiv_prompt('search_select_dates_system.md')

            # Run three calls in parallel
            import asyncio
            rewrite_task = asyncio.create_task(or_get_llm_response([
                {"role": "system", "content": rewrite_sys},
                {"role": "user", "content": original_query},
            ], model="openai/gpt-oss-120b"))
            # cats_input = f"Query: {original_query}\n\nValid categories (examples): {', '.join(cats[:100])} ..."
            # cats_task = asyncio.create_task(or_get_json_response(system_prompt=cats_sys, user_prompt=cats_input, model="openai/gpt-oss-120b"))
            # dates_input = f"Query: {original_query}"
            # dates_task = asyncio.create_task(or_get_json_response(system_prompt=dates_sys, user_prompt=dates_input, model="openai/gpt-oss-120b"))

            # rewrite_res, cats_res, dates_res = await asyncio.gather(rewrite_task, cats_task, dates_task, return_exceptions=True)
            rewrite_res = await rewrite_task

            # Handle rewrite result
            if not isinstance(rewrite_res, Exception):
                text = (rewrite_res.response_text or '').strip() if rewrite_res else ''
                if text:
                    rewritten_query = text

            # # Handle categories JSON (bypassed for now)
            # if not isinstance(cats_res, Exception):
            #     data_c = getattr(cats_res, 'parsed_json', None) or {}
            #     if isinstance(data_c.get('selected_categories'), list) and data_c['selected_categories']:
            #         applied_categories = [str(x) for x in data_c['selected_categories'] if isinstance(x, (str, int))]
            #     try:
            #         logger.info(
            #             "LLM categories output: generation_id=%s raw_len=%s parsed=%s applied=%s",
            #             getattr(cats_res, 'generation_id', None),
            #             len((getattr(cats_res, 'response_text', None) or '')),
            #             data_c,
            #             applied_categories,
            #         )
            #     except Exception:
            #         pass
            # else:
            #     try:
            #         logger.exception("LLM categories selection failed with exception: %s", cats_res)
            #     except Exception:
            #         pass

            # # Handle dates JSON (bypassed for now)
            # if not isinstance(dates_res, Exception):
            #     data_d = getattr(dates_res, 'parsed_json', None) or {}
            #     df = data_d.get('date_from')
            #     dt = data_d.get('date_to')
            #     if applied_date_from is None and isinstance(df, str):
            #         applied_date_from = df
            #     if applied_date_to is None and isinstance(dt, str):
            #         applied_date_to = dt
            #     try:
            #         logger.info(
            #             "LLM dates output: generation_id=%s raw_len=%s parsed=%s applied_from=%s applied_to=%s",
            #             getattr(dates_res, 'generation_id', None),
            #             len((getattr(dates_res, 'response_text', None) or '')),
            #             data_d,
            #             applied_date_from,
            #             applied_date_to,
            #         )
            #     except Exception:
            #         pass
            # else:
            #     try:
            #         logger.exception("LLM dates selection failed with exception: %s", dates_res)
            #     except Exception:
            #         pass

            try:
                logger.info(
                    "User search LLM parallel: rewritten=%s cats=%s dates=%s→%s",
                    bool(rewritten_query),
                    (applied_categories or [])[:5],
                    applied_date_from,
                    applied_date_to,
                )
            except Exception:
                pass
        except Exception:
            logger.exception("Parallel LLM selection failed; proceeding without it")

    # Step B: Embed query via Voyage
    query_text = (rewritten_query or original_query)
    # Ensure query embedding matches the collection dimension
    try:
        logger.info("Embedding query text len=%s rewritten=%s", len(query_text), bool(rewritten_query))
    except Exception:
        pass
    query_vector = await voyage_embed_query(query_text, output_dimension=2048)
    if not query_vector:
        return [], {"error": "embed_failed"}

    # Step C: Qdrant vector search with filters
    date_from_ts = _to_epoch_seconds(applied_date_from)
    date_to_ts = _to_epoch_seconds(applied_date_to)
    initial_k = max(limit, min(rerank_top_k, 200))
    # Ensure collection exists (domain-owned): arxiv_papers, 2048-dim, cosine distance
    try:
        qdrant_ensure_collection(vector_size=2048, collection="arxiv_papers")
    except Exception:
        logger.exception("Failed to ensure Qdrant collection arxiv_papers")
    raw_hits = qdrant_search_by_vector(
        query_vector=query_vector,
        limit=initial_k,
        categories=applied_categories,
        date_from_ts=date_from_ts,
        date_to_ts=date_to_ts,
        collection="arxiv_papers",
    )
    try:
        logger.info(
            "Qdrant returned hits=%s for query (limit=%s, rerank_top_k=%s) cats=%s",
            len(raw_hits),
            limit,
            rerank_top_k,
            (applied_categories or [])[:5],
        )
    except Exception:
        pass

    if not raw_hits:
        return [], {"rewritten_query": rewritten_query, "applied_categories": applied_categories, "applied_date_from": applied_date_from, "applied_date_to": applied_date_to}

    # Step D: Rerank candidates strictly using summary text only
    documents: List[str] = []
    doc_to_hit_index: List[int] = []
    for idx, h in enumerate(raw_hits):
        payload = h.payload or {}
        summary = payload.get('summary')
        if isinstance(summary, str):
            summary = summary.strip()
        if summary:
            documents.append(summary)
            doc_to_hit_index.append(idx)
    try:
        logger.info("Documents prepared for rerank=%s (from hits=%s)", len(documents), len(raw_hits))
    except Exception:
        pass

    # If no summaries available, return empty result (no guessing / no fallback)
    if not documents:
        logger.error("Rerank skipped: no summaries available in Qdrant payloads (documents=0)")
        return [], {
            "rewritten_query": rewritten_query,
            "applied_categories": applied_categories,
            "applied_date_from": applied_date_from,
            "applied_date_to": applied_date_to,
        }

    try:
        top_k = min(limit, len(documents))
        rr = await voyage_rerank(query=query_text, documents=documents, top_k=top_k)
        order = rr.items or []
        out: List[Dict[str, Any]] = []
        if order:
            # Build results in rerank order
            for item in order:
                doc_idx = item.index
                if 0 <= doc_idx < len(doc_to_hit_index):
                    hit_idx = doc_to_hit_index[doc_idx]
                    hit = raw_hits[hit_idx]
                    out.append({
                        "point": {"id": hit.id, "payload": hit.payload},
                        "qdrant_score": hit.score,
                        "rerank_score": item.score,
                    })
                else:
                    try:
                        logger.warning("Rerank index out of range: doc_idx=%s docs=%s", doc_idx, len(doc_to_hit_index))
                    except Exception:
                        pass
        else:
            # Reranker returned nothing; log and fall back to Qdrant order
            logger.error("Reranker returned no items; falling back to Qdrant order (hits=%s, docs=%s)", len(raw_hits), len(documents))
            out = [
                {"point": {"id": h.id, "payload": h.payload}, "qdrant_score": h.score, "rerank_score": None}
                for h in raw_hits[:limit]
            ]
        try:
            logger.info("Returning results: count=%s (limited to %s)", len(out[:limit]), limit)
        except Exception:
            pass
        return out[:limit], {
            "rewritten_query": rewritten_query,
            "applied_categories": applied_categories,
            "applied_date_from": applied_date_from,
            "applied_date_to": applied_date_to,
        }
    except Exception:
        logger.exception("Rerank failed; falling back to Qdrant order")
        out_fb: List[Dict[str, Any]] = [
            {"point": {"id": h.id, "payload": h.payload}, "qdrant_score": h.score, "rerank_score": None}
            for h in raw_hits[:limit]
        ]
        try:
            logger.info("Returning fallback results: count=%s (limited to %s)", len(out_fb), limit)
        except Exception:
            pass
        return out_fb, {
            "rewritten_query": rewritten_query,
            "applied_categories": applied_categories,
            "applied_date_from": applied_date_from,
            "applied_date_to": applied_date_to,
        }


async def find_similar_papers(
    paper_uuid: str,
    limit: int = 20,
    categories: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Find similar papers by vector only (no date filters, no reranking).
    Excludes the focal paper from results.
    Returns list of { point, qdrant_score } in Qdrant order.
    """
    if not paper_uuid:
        return []
    vec = qdrant_get_vector_by_id(paper_uuid)
    if not vec:
        try:
            logger.warning("Similar papers: vector not found for id=%s", str(paper_uuid))
        except Exception:
            pass
        return []
    # Ensure collection exists before searching
    try:
        qdrant_ensure_collection(vector_size=2048, collection="arxiv_papers")
    except Exception:
        logger.exception("Failed to ensure Qdrant collection arxiv_papers")
    hits = qdrant_search_by_vector(query_vector=vec, limit=max(1, limit + 1), categories=categories, collection="arxiv_papers")
    try:
        logger.info("Similar papers: initial hits=%s (requested limit=%s)", len(hits), limit)
    except Exception:
        pass
    out: List[Dict[str, Any]] = []
    for h in hits:
        if str(h.id) == str(paper_uuid):
            continue
        out.append({"point": {"id": h.id, "payload": h.payload}, "qdrant_score": h.score})
        if len(out) >= limit:
            break
    try:
        logger.info("Similar papers: returning=%s", len(out))
    except Exception:
        pass
    return out

