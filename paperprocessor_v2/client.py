import logging
import base64
import io
from typing import Optional

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
