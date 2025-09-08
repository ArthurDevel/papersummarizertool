import logging
import json
import os
import re
from typing import Dict, Any, List, Optional

from shared.openrouter import client as openrouter_client
from paperprocessor_v2.models import ProcessedDocument, Header

logger = logging.getLogger(__name__)

### CONSTANTS ###
STRUCTURE_MODEL = "google/gemini-2.5-pro"
EXTRACTION_MODEL = "google/gemini-2.5-flash"
MAX_STRUCTURE_PAGES = 20


### HELPER FUNCTIONS ###
def _load_structure_analysis_prompt() -> str:
    """Load the document structure analysis prompt."""
    prompts_dir = os.path.join(os.path.dirname(__file__), '..', 'prompts')
    prompt_path = os.path.join(prompts_dir, 'analyze_document_structure.md')
    
    try:
        with open(prompt_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        raise RuntimeError(f"Structure analysis prompt not found: {prompt_path}")


def _load_header_extraction_prompt() -> str:
    """Load the header extraction prompt template."""
    prompts_dir = os.path.join(os.path.dirname(__file__), '..', 'prompts')
    prompt_path = os.path.join(prompts_dir, 'extract_page_headers.md')
    
    try:
        with open(prompt_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        raise RuntimeError(f"Header extraction prompt not found: {prompt_path}")


def _create_structure_analysis_prompt_parts(pages_base64: List[str]) -> List[Dict[str, Any]]:
    """Create multimodal prompt parts for document structure analysis."""
    prompt_parts = [
        {"type": "text", "text": "Analyze the structure of this research paper and identify all structural elements:"}
    ]
    
    # Add each page image
    for page_base64 in pages_base64:
        prompt_parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{page_base64}"}
        })
    
    return prompt_parts


def _create_header_extraction_prompt_with_structure(structure_data: Dict[str, Any]) -> str:
    """Create detailed header extraction prompt based on structure analysis."""
    base_prompt = _load_header_extraction_prompt()
    
    # Add structure reference to the prompt
    structure_reference = "\n\nDOCUMENT STRUCTURE REFERENCE:\n"
    
    for element in structure_data.get('elements', []):
        structure_reference += f"\n**{element['element_type']}** (Level {element['level']})"
        structure_reference += f"\n  Recognition: {element['recognition_pattern']}"
        examples = element.get('examples', [])[:2]  # Take first 2 examples
        structure_reference += f"\n  Examples: {', '.join(examples)}"
        structure_reference += "\n"
    
    return base_prompt + structure_reference


def _parse_json_with_fallback(content: str, context: str) -> Dict[str, Any]:
    """Parse JSON content with fallback handling for malformed responses."""
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        logger.warning(f"JSON parsing failed for {context}: {e.msg}")
        
        # Try to extract JSON from response if wrapped in other text
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                logger.error(f"Extracted JSON also failed for {context}")
                
        # Return empty fallback
        if context.startswith("structure"):
            return {"document_type": "research_paper", "elements": [], "notes": "JSON parsing failed"}
        else:  # header extraction context
            return {"headers": []}


def _find_header_line_in_markdown(header_text: str, markdown_content: str) -> Optional[int]:
    """
    Find the line number where a header appears in markdown content.
    
    Args:
        header_text: The header text to search for
        markdown_content: The markdown content to search in
        
    Returns:
        Line number (0-based) where header appears, or None if not found
    """
    if not markdown_content or not header_text:
        return None
    
    lines = markdown_content.split('\n')
    header_text_clean = header_text.strip().lower()
    
    for i, line in enumerate(lines):
        line_clean = line.strip().lower()
        
        # Direct match
        if header_text_clean in line_clean:
            return i
        
        # Try removing markdown formatting (# symbols, ** bold, etc.)
        line_no_markdown = line_clean.lstrip('#').strip().replace('**', '').replace('*', '')
        if header_text_clean in line_no_markdown or line_no_markdown in header_text_clean:
            return i
    
    return None


def _validate_and_clean_headers(headers_data: List[Dict[str, Any]], page_number: int) -> List[Dict[str, Any]]:
    """Validate and clean headers data from API response."""
    valid_headers = []
    
    for i, header in enumerate(headers_data):
        if not isinstance(header, dict):
            logger.warning(f"Header {i+1} on page {page_number} is not a dict, skipping")
            continue
        
        # Check required fields
        required_fields = ["text", "element_type", "level"]
        missing_fields = [field for field in required_fields if field not in header or header[field] is None]
        
        if missing_fields:
            logger.warning(f"Header {i+1} on page {page_number} missing fields {missing_fields}, skipping")
            raise RuntimeError(f"Header {i+1} on page {page_number} missing fields {missing_fields}")
        
        # Validate level is an integer
        if not isinstance(header["level"], int):
            logger.warning(f"Header {i+1} on page {page_number} has invalid level '{header['level']}', skipping")
            raise RuntimeError(f"Header {i+1} on page {page_number} has invalid level '{header['level']}'")
        
        # Clean and validate text
        header_text = str(header["text"]).strip()
        if not header_text:
            logger.warning(f"Header {i+1} on page {page_number} has empty text, skipping")
            raise RuntimeError(f"Header {i+1} on page {page_number} has empty text")
        
        valid_headers.append({
            "text": header_text,
            "element_type": str(header["element_type"]).strip(),
            "level": int(header["level"]),
            "page_number": page_number
        })
    
    return valid_headers


async def _analyze_document_structure(pages_base64: List[str]) -> Dict[str, Any]:
    """
    Step 3a: Analyze document structure from first pages.
    
    Args:
        pages_base64: List of base64-encoded page images
        
    Returns:
        Document structure analysis results
    """
    logger.info(f"Analyzing document structure from {len(pages_base64)} pages")
    
    # Step 1: Prepare API call for structure analysis
    system_prompt = _load_structure_analysis_prompt()
    user_prompt_parts = _create_structure_analysis_prompt_parts(pages_base64)
    
    # Step 2: Call OpenRouter API for structure analysis
    response = await openrouter_client.get_multimodal_json_response(
        system_prompt=system_prompt,
        user_prompt_parts=user_prompt_parts,
        model=STRUCTURE_MODEL
    )
    
    # Step 3: Parse structure response with error handling
    structure_data = _parse_json_with_fallback(
        response.parsed_json if isinstance(response.parsed_json, str) else json.dumps(response.parsed_json),
        "structure analysis"
    )
    
    logger.info(f"Found {len(structure_data.get('elements', []))} element types in document")
    return structure_data


async def _extract_headers_from_page(page_base64: str, page_number: int, extraction_prompt: str, page_markdown: Optional[str] = None) -> List[Header]:
    """
    Extract headers from a single page.
    
    Args:
        page_base64: Base64-encoded page image
        page_number: Page number (1-based)
        extraction_prompt: Detailed extraction prompt with structure info
        page_markdown: OCR markdown content for line number detection
        
    Returns:
        List of Header objects found on this page
    """
    # Step 1: Create single-page prompt
    user_prompt_parts = [
        {"type": "text", "text": extraction_prompt},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{page_base64}"}}
    ]
    
    # Step 2: Call OpenRouter API for header extraction
    response = await openrouter_client.get_multimodal_json_response(
        system_prompt="You are an expert at extracting headers from research paper pages.",
        user_prompt_parts=user_prompt_parts,
        model=EXTRACTION_MODEL
    )
    
    # Step 3: Parse and validate response
    page_data = _parse_json_with_fallback(
        response.parsed_json if isinstance(response.parsed_json, str) else json.dumps(response.parsed_json),
        f"page {page_number} header extraction"
    )
    
    # Step 4: Validate and clean headers
    headers_data = page_data.get("headers", [])
    valid_headers_data = _validate_and_clean_headers(headers_data, page_number)
    
    # Step 5: Convert to Header objects
    headers = []
    for header_data in valid_headers_data:
        # Find markdown line number if page markdown is available
        markdown_line_number = None
        if page_markdown:
            markdown_line_number = _find_header_line_in_markdown(header_data["text"], page_markdown)
        
        header = Header(
            text=header_data["text"],
            level=header_data["level"],
            page_number=page_number,
            markdown_line_number=markdown_line_number
        )
        headers.append(header)
    
    logger.info(f"Page {page_number}: found {len(headers)} valid headers")
    return headers


async def extract_structure(document: ProcessedDocument) -> None:
    """
    Step 3: Extract structural elements (headers) from the processed document.
    Uses a two-step approach: analyze structure, then extract headers per page.
    Modifies the document in place.
    """
    logger.info("Starting structural elements extraction...")
    
    if not document.pages:
        logger.warning("No pages available for structure extraction")
        return
    
    # Step 1: Get pages for structure analysis (first MAX_STRUCTURE_PAGES)
    structure_pages = document.pages[:MAX_STRUCTURE_PAGES]
    structure_pages_base64 = []
    
    for page in structure_pages:
        if page.img_base64:
            structure_pages_base64.append(page.img_base64)
        else:
            logger.warning(f"Page {page.page_number} missing img_base64 for structure analysis")
            raise RuntimeError(f"Page {page.page_number} missing img_base64")
    
    logger.info(f"Using first {len(structure_pages_base64)} pages for structure analysis")
    
    # Step 2: Analyze document structure
    try:
        structure_data = await _analyze_document_structure(structure_pages_base64)
    except Exception as e:
        logger.error(f"Document structure analysis failed: {e}")
        raise RuntimeError(f"Structure analysis failed: {e}") from e
    
    # Step 3: Create extraction prompt with structure information
    extraction_prompt = _create_header_extraction_prompt_with_structure(structure_data)
    
    # Step 4: Extract headers from each page
    all_headers = []
    
    for page in document.pages:
        if not page.img_base64:
            logger.warning(f"Page {page.page_number} missing img_base64 for header extraction")
            raise RuntimeError(f"Page {page.page_number} missing img_base64")
        
        try:
            page_headers = await _extract_headers_from_page(
                page.img_base64,
                page.page_number,
                extraction_prompt,
                page.ocr_markdown
            )
            all_headers.extend(page_headers)
            
        except Exception as e:
            logger.error(f"Header extraction failed for page {page.page_number}: {e}")
            raise RuntimeError(f"Header extraction failed for page {page.page_number}: {e}") from e
    
    # Step 5: Update document with extracted headers
    document.headers = all_headers
    
    logger.info(f"Successfully extracted {len(all_headers)} headers from {len(document.pages)} pages")
