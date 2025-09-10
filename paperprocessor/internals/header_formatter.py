import logging
import os
from typing import Dict, List

from paperprocessor.models import ProcessedDocument, Header

logger = logging.getLogger(__name__)


### HELPER FUNCTIONS ###
def _write_debug_output(content: str, filename: str) -> None:
    """
    Write debugging content to file in the debugging output directory.
    
    Args:
        content: The content to write to the file
        filename: Name of the output file
    """
    # Create path relative to this file's location
    debug_dir = os.path.join(os.path.dirname(__file__), '..', 'debugging_output')
    os.makedirs(debug_dir, exist_ok=True)
    
    # Write the content to the specified file
    file_path = os.path.join(debug_dir, filename)
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    logger.info(f"Debug output written to {file_path}")


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


def _add_section_tags_to_page_markdown(original_markdown: str, page_headers: List[Header]) -> str:
    """
    Add section tags to markdown by inserting <<section>> before document_section and document_section_references headers.
    
    Args:
        original_markdown: Original OCR markdown content
        page_headers: Headers found on this page
        
    Returns:
        Markdown with section tags added
    """
    if not original_markdown or not page_headers:
        return original_markdown or ""
    
    # Split markdown into lines
    lines = original_markdown.split('\n')
    
    # Find document_section and document_section_references headers that have line numbers
    section_headers_by_line: Dict[int, Header] = {}
    for header in page_headers:
        if (header.markdown_line_number is not None and 
            header.element_type in ['document_section', 'document_section_references']):
            section_headers_by_line[header.markdown_line_number] = header
    
    # Insert section tags before document_section and document_section_references headers
    # Work backwards to avoid line number shifts
    for line_number in sorted(section_headers_by_line.keys(), reverse=True):
        header = section_headers_by_line[line_number]
        if 0 <= line_number < len(lines):
            lines.insert(line_number, "<<section>>")
            logger.debug(f"Added section tag before header on line {line_number}: '{header.text}'")
    
    return '\n'.join(lines)


def _format_page_markdown(original_markdown: str, page_headers: List[Header]) -> str:
    """
    Format markdown by replacing header lines with properly formatted versions.
    (KEPT FOR FUTURE USE - currently not called)
    
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
    Step 4: Add section tags to document markdown.
    Inserts <<section>> tags before all document_section and document_section_references headers.
    Creates document.final_markdown by combining all pages.
    Preserves original OCR markdown in pages.
    """
    logger.info("Adding section tags to document...")
    
    if not document.headers:
        logger.info("No headers found in document, creating final_markdown from OCR content")
        # Combine all OCR markdown even if no headers
        page_markdowns = []
        for page in document.pages:
            if page.ocr_markdown:
                page_markdowns.append(page.ocr_markdown)
        document.final_markdown = '\n\n'.join(page_markdowns)
        
        # Write final markdown to debug output even if no headers
        if document.final_markdown:
            _write_debug_output(document.final_markdown, "header_formatter_final_markdown.md")
        
        return
    
    # Step 1: Process each page to add section tags
    page_markdowns = []
    total_section_tags_added = 0
    
    for page in document.pages:
        if not page.ocr_markdown:
            logger.warning(f"Page {page.page_number} has no OCR markdown, skipping")
            continue
        
        # Step 2: Get headers for this page
        page_headers = _get_page_headers(document.headers, page.page_number)
        
        # Step 3: Add section tags to page markdown
        page_markdown_with_tags = _add_section_tags_to_page_markdown(page.ocr_markdown, page_headers)
        page_markdowns.append(page_markdown_with_tags)
        
        # Count section headers on this page
        section_headers = [h for h in page_headers if h.element_type in ['document_section', 'document_section_references'] and h.markdown_line_number is not None]
        total_section_tags_added += len(section_headers)
        
        if section_headers:
            logger.info(f"Page {page.page_number}: added {len(section_headers)} section tags")
        else:
            logger.debug(f"Page {page.page_number}: no section headers found")
    
    # Step 4: Combine all pages into final_markdown
    document.final_markdown = '\n\n'.join(page_markdowns)
    
    # Step 4a: Write final markdown to debug output
    if document.final_markdown:
        _write_debug_output(document.final_markdown, "header_formatter_final_markdown.md")
    
    # Step 5: Log summary
    total_section_headers = [h for h in document.headers if h.element_type in ['document_section', 'document_section_references']]
    section_headers_with_line_numbers = [h for h in total_section_headers if h.markdown_line_number is not None]
    section_headers_without_line_numbers = [h for h in total_section_headers if h.markdown_line_number is None]
    
    logger.info(f"Section tagging completed: {total_section_tags_added} section tags added, {len(section_headers_without_line_numbers)} section headers without line numbers")
    
    if section_headers_without_line_numbers:
        logger.warning(f"Section headers without line numbers: {[h.text for h in section_headers_without_line_numbers]}")
