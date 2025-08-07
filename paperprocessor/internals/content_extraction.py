from typing import List, Dict, Any
from PIL import Image
import base64
import io
import logging

from shared.services.openrouter_service import openrouter_service
from paperprocessor.internals.prompt_loader import load_prompt

logger = logging.getLogger(__name__)

def _image_to_base64(image: Image.Image) -> str:
    """Converts a PIL Image to a base64 encoded string."""
    buffered = io.BytesIO()
    image.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode('utf-8')

async def extract_initial_content(images: List[Image.Image]) -> Dict[str, Any]:
    """
    Processes a list of page images to extract headers, asset locations, and asset mentions.

    Args:
        images: A list of PIL Image objects for each page of the PDF.

    Returns:
        A dictionary containing the extracted content: `headers`, `asset_locations`, `asset_mentions`.
    """
    logger.info(f"Starting initial content extraction for {len(images)} pages.")
    
    try:
        system_prompt = load_prompt("1_extract_content.md")
        
        user_prompt_parts = [
            {"type": "text", "text": "Here are the pages of the document. Please analyze them and provide the requested JSON output."}
        ] + [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{_image_to_base64(img)}"}}
            for img in images
        ]

        response = await openrouter_service.get_multimodal_json_response(
            system_prompt=system_prompt,
            user_prompt_parts=user_prompt_parts,
            model="anthropic/claude-3.5-sonnet"
        )
        
        logger.info("Successfully extracted initial content.")
        # Basic validation
        if "headers" not in response or "asset_locations" not in response or "asset_mentions" not in response:
            raise ValueError("Invalid response format from content extraction LLM.")
            
        return response
    except Exception as e:
        logger.error(f"Failed during initial content extraction: {e}")
        raise 