import logging

from paperprocessor_v2.models import ProcessedDocument

logger = logging.getLogger(__name__)


async def rewrite_sections(document: ProcessedDocument) -> None:
    """
    Step 6: Rewriting per section.
    Combine all pages and rewrite the content to produce the final markdown.
    Modifies the document in place.
    """
    logger.info("Rewriting sections...")
    
    # Combine all structured markdown from pages
    combined_markdown = "\n\n".join([page.structured_markdown or "" for page in document.pages])
    
    # TODO: Use LLM to rewrite sections for better readability and coherence
    document.final_markdown = combined_markdown
    
    logger.info("Section rewriting completed.")
