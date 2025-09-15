import logging
import base64
import io
import time
import os
import json
from typing import Optional, Dict, Any, List

from paperprocessor.models import ProcessedDocument, ProcessedPage, ApiCallCostForStep
from paperprocessor.internals.pdf_to_image import convert_pdf_to_images
from paperprocessor.internals.mistral_ocr import extract_markdown_from_pages
from paperprocessor.internals.metadata_extractor import extract_metadata
from paperprocessor.internals.structure_extractor import extract_structure
from paperprocessor.internals.header_formatter import format_headers
from paperprocessor.internals.section_rewriter import rewrite_sections
from shared.db import SessionLocal
from papers.client import get_paper_metadata, get_processed_result_path

logger = logging.getLogger(__name__)


### HELPER FUNCTIONS ###
def _calculate_usage_summary(step_costs: List[ApiCallCostForStep]) -> Dict[str, Any]:
    """
    Aggregate ApiCallCostForStep objects into UsageSummary format.
    Business logic for cost aggregation - belongs in client.py, not models.py.
    """
    if not step_costs:
        return {}
    
    total_cost = 0.0
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_tokens = 0
    by_model: Dict[str, Dict[str, Any]] = {}
    
    for step_cost in step_costs:
        cost = step_cost.cost_info
        
        # Aggregate totals
        if cost.total_cost:
            total_cost += cost.total_cost
        if cost.prompt_tokens:
            total_prompt_tokens += cost.prompt_tokens
        if cost.completion_tokens:
            total_completion_tokens += cost.completion_tokens
        if cost.total_tokens:
            total_tokens += cost.total_tokens
            
        # Aggregate by model
        model = step_cost.model
        if model not in by_model:
            by_model[model] = {
                "num_calls": 0,
                "total_cost": 0.0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            }
        
        by_model[model]["num_calls"] += 1
        if cost.total_cost:
            by_model[model]["total_cost"] += cost.total_cost
        if cost.prompt_tokens:
            by_model[model]["prompt_tokens"] += cost.prompt_tokens
        if cost.completion_tokens:
            by_model[model]["completion_tokens"] += cost.completion_tokens
        if cost.total_tokens:
            by_model[model]["total_tokens"] += cost.total_tokens
    
    return {
        "currency": "USD",
        "total_cost": total_cost if total_cost > 0 else None,
        "total_prompt_tokens": total_prompt_tokens if total_prompt_tokens > 0 else None,
        "total_completion_tokens": total_completion_tokens if total_completion_tokens > 0 else None,
        "total_tokens": total_tokens if total_tokens > 0 else None,
        "by_model": by_model
    }




def _load_usage_summary_from_json(paper_uuid: str) -> Optional[Dict[str, Any]]:
    """Load usage summary data from processed result JSON file."""
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
        paper = get_paper_metadata(session, paper_uuid)
        if paper.status != 'completed':
            raise RuntimeError("Paper not completed")
        if not paper.initiated_by_user_id or paper.initiated_by_user_id != auth_provider_id:
            raise PermissionError("Not authorized to view metrics for this paper")
        usage_summary = _load_usage_summary_from_json(paper.paper_uuid)
        return {
            "paper_uuid": paper.paper_uuid,
            "status": paper.status,
            "created_at": paper.created_at,
            "started_at": paper.started_at,
            "finished_at": paper.finished_at,
            "num_pages": paper.num_pages,
            "processing_time_seconds": paper.processing_time_seconds,
            "total_cost": paper.total_cost,
            "avg_cost_per_page": paper.avg_cost_per_page,
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
        paper = get_paper_metadata(session, paper_uuid)
        if paper.status != 'completed':
            raise RuntimeError("Paper not completed")
        usage_summary = _load_usage_summary_from_json(paper.paper_uuid)
        return {
            "paper_uuid": paper.paper_uuid,
            "status": paper.status,
            "created_at": paper.created_at,
            "started_at": paper.started_at,
            "finished_at": paper.finished_at,
            "num_pages": paper.num_pages,
            "processing_time_seconds": paper.processing_time_seconds,
            "total_cost": paper.total_cost,
            "avg_cost_per_page": paper.avg_cost_per_page,
            "usage_summary": usage_summary,
            "initiated_by_user_id": paper.initiated_by_user_id,
        }
    finally:
        session.close()


async def process_paper_pdf(pdf_contents: bytes, paper_id: Optional[str] = None) -> ProcessedDocument:
        """
        5-step pipeline:
        1. OCR → markdown per page
        2. Extract metadata  
        3. Extract structural elements
        4. Format headers
        5. Rewrite sections
        """
        logger.info("Paper processing pipeline v2 started.")
        
        # Create ProcessedDocument DTO with PDF base64
        pdf_base64 = base64.b64encode(pdf_contents).decode('utf-8')
        
        logger.info("Converting PDF to images for page image storage...")
        images = await convert_pdf_to_images(pdf_contents)
        
        # Create ProcessedPages with base64 encoded images
        pages = []
        for i, image in enumerate(images):
            page_num = i + 1
            
            # Convert PIL Image to base64
            buffered = io.BytesIO()
            image.save(buffered, format="PNG")
            img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
            
            page = ProcessedPage(
                page_number=page_num,
                img_base64=img_base64
            )
            pages.append(page)
        
        document = ProcessedDocument(
            pdf_base64=pdf_base64,
            pages=pages
        )
        
        # Step 1: OCR pages to markdown - populates ocr_markdown
        logger.info("Step 1: OCR pages to markdown.")
        await extract_markdown_from_pages(document)
        
        # Step 2: Extract metadata (title, authors) - modifies document in place
        logger.info("Step 2: Extracting metadata.")
        await extract_metadata(document)
        
        # Step 3: Extract structural elements (headers) - modifies document in place
        logger.info("Step 3: Extracting structural elements.")
        await extract_structure(document)
        
        # Step 4: Format headers to # levels - modifies document in place
        logger.info("Step 4: Formatting headers.")
        await format_headers(document)
        
        # Step 5: Rewrite sections - modifies document in place
        logger.info("Step 5: Rewriting sections.")
        await rewrite_sections(document)
        
        logger.info("Paper processing pipeline v2 finished.")
        return document


async def process_paper_pdf_legacy(pdf_contents: bytes, paper_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Legacy-shaped adapter for callers expecting the v1 dict structure.
        Keeps v2 as-is and maps its DTO to the expected fields.
        """
        _t0 = time.perf_counter()

        # Run v2 processing
        doc: ProcessedDocument = await process_paper_pdf(pdf_contents, paper_id)

        # Helper to build data URL for a base64-encoded PNG
        def _as_data_url_png(b64: str) -> str:
            return f"data:image/png;base64,{b64}"

        # Pages list in legacy format
        pages: List[Dict[str, Any]] = []
        for idx, page in enumerate(doc.pages):
            pages.append({
                "page_number": idx + 1,
                "image_data_url": _as_data_url_png(page.img_base64),
            })

        # Thumbnail: use full first page image as a simple thumbnail
        thumbnail_data_url: Optional[str] = None
        if doc.pages:
            thumbnail_data_url = _as_data_url_png(doc.pages[0].img_base64)

        # Sections: flat list of rewritten contents
        sections: List[Dict[str, Any]] = []
        for s in doc.sections:
            sections.append({
                "rewritten_content": s.rewritten_content,
            })

        # Metrics
        processing_time_seconds = max(0.0, time.perf_counter() - _t0)
        num_pages = len(doc.pages)
        
        # Calculate usage summary from collected step costs
        usage_summary = _calculate_usage_summary(doc.step_costs)
        total_cost = usage_summary.get("total_cost")
        avg_cost_per_page = (total_cost / num_pages) if total_cost and num_pages > 0 else None

        result: Dict[str, Any] = {
            "paper_id": paper_id or "temp_id",
            "title": doc.title,
            "authors": doc.authors,
            "thumbnail_data_url": thumbnail_data_url,
            "sections": sections,
            "tables": [],
            "figures": [],
            "pages": pages,
            "usage_summary": usage_summary,
            "processing_time_seconds": processing_time_seconds,
            "num_pages": num_pages,
            "total_cost": total_cost,
            "avg_cost_per_page": avg_cost_per_page,
        }

        return result
