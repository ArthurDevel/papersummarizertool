import logging
from typing import Dict, List

from paperprocessor_v2.models import ProcessedDocument, Header

logger = logging.getLogger(__name__)


### HELPER FUNCTIONS ###
def _format_header_line(header: Header) -> str:
    """
    Format a header with the appropriate number of # symbols.
    
    Args:
        header: Header object with text and level
        
    Returns:
        Properly formatted markdown header line
    """
    # Convert level to # symbols (level 1 = #, level 2 = ##, etc.)
    hash_symbols = "#" * header.level
    return f"{hash_symbols} {header.text.strip()}"


def _get_page_headers(document_headers: List[Header], page_number: int) -> List[Header]:
    """
    Get all headers that belong to a specific page.
    
    Args:
        document_headers: All headers in the document
        page_number: Page number to filter by
        
    Returns:
        List of headers for the specified page
    """
    return [header for header in document_headers if header.page_number == page_number]


def _format_page_markdown(original_markdown: str, page_headers: List[Header]) -> str:
    """
    Format markdown by replacing header lines with properly formatted versions.
    
    Args:
        original_markdown: Original OCR markdown content
        page_headers: Headers found on this page
        
    Returns:
        Markdown with properly formatted headers
    """
    if not original_markdown or not page_headers:
        return original_markdown or ""
    
    # Split markdown into lines
    lines = original_markdown.split('\n')
    
    # Create a dictionary of line numbers to format
    headers_by_line: Dict[int, Header] = {}
    for header in page_headers:
        if header.markdown_line_number is not None:
            headers_by_line[header.markdown_line_number] = header
    
    # Replace header lines with formatted versions
    for line_number, header in headers_by_line.items():
        if 0 <= line_number < len(lines):
            formatted_line = _format_header_line(header)
            lines[line_number] = formatted_line
            logger.debug(f"Formatted header on line {line_number}: '{header.text}' -> '{formatted_line}'")
    
    return '\n'.join(lines)


async def format_headers(document: ProcessedDocument) -> None:
    """
    Step 4: Reformat headers to fit levels.
    level 1 -> #
    level 2 -> ##
    level 3 -> ###
    etc.
    Modifies the document pages in place.
    """
    logger.info("Formatting headers to markdown levels...")
    
    if not document.headers:
        logger.info("No headers found in document, skipping formatting")
        return
    
    # Process each page
    for page in document.pages:
        if not page.ocr_markdown:
            logger.warning(f"Page {page.page_number} has no OCR markdown, skipping")
            continue
        
        # Get headers for this page
        page_headers = _get_page_headers(document.headers, page.page_number)
        
        if not page_headers:
            # No headers on this page, just copy OCR markdown to structured markdown
            page.structured_markdown = page.ocr_markdown
            logger.debug(f"Page {page.page_number}: no headers, copying OCR markdown")
        else:
            # Format headers on this page
            page.structured_markdown = _format_page_markdown(page.ocr_markdown, page_headers)
            logger.info(f"Page {page.page_number}: formatted {len(page_headers)} headers")
    
    # Count total headers processed
    headers_with_line_numbers = [h for h in document.headers if h.markdown_line_number is not None]
    headers_without_line_numbers = [h for h in document.headers if h.markdown_line_number is None]
    
    logger.info(f"Header formatting completed: {len(headers_with_line_numbers)} headers formatted, {len(headers_without_line_numbers)} headers without line numbers")
    
    if headers_without_line_numbers:
        logger.warning(f"Headers without line numbers: {[h.text for h in headers_without_line_numbers]}")
