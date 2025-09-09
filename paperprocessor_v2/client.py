import logging
import base64
import io
import time
from typing import Optional, Dict, Any, List

from paperprocessor_v2.models import ProcessedDocument, ProcessedPage
from paperprocessor_v2.internals.pdf_to_image import convert_pdf_to_images
from paperprocessor_v2.internals.mistral_ocr import extract_markdown_from_pages
from paperprocessor_v2.internals.metadata_extractor import extract_metadata
from paperprocessor_v2.internals.structure_extractor import extract_structure
from paperprocessor_v2.internals.header_formatter import format_headers
from paperprocessor_v2.internals.section_rewriter import rewrite_sections

logger = logging.getLogger(__name__)


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

        result: Dict[str, Any] = {
            "paper_id": paper_id or "temp_id",
            "title": doc.title,
            "authors": doc.authors,
            "thumbnail_data_url": thumbnail_data_url,
            "sections": sections,
            "tables": [],
            "figures": [],
            "pages": pages,
            "usage_summary": {},
            "processing_time_seconds": processing_time_seconds,
            "num_pages": num_pages,
            "total_cost": None,
            "avg_cost_per_page": None,
        }

        return result
