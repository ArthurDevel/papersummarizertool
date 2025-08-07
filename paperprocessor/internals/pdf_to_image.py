from typing import List
import fitz  # PyMuPDF
from PIL import Image
import io
import logging

logger = logging.getLogger(__name__)

def convert_pdf_to_images(pdf_bytes: bytes) -> List[Image.Image]:
    """
    Converts a PDF document into a list of PIL Image objects.

    Args:
        pdf_bytes: The byte content of the PDF file.

    Returns:
        A list of PIL Image objects, one for each page of the PDF.
    """
    try:
        pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
        images = []
        for page_num in range(len(pdf_document)):
            page = pdf_document.load_page(page_num)
            
            # Render page to a pixmap (an image)
            # The higher the dpi, the higher the resolution
            pix = page.get_pixmap(dpi=300)
            
            # Convert pixmap to a PIL Image
            img_bytes = pix.tobytes("png")
            image = Image.open(io.BytesIO(img_bytes))
            images.append(image)
            
        logger.info(f"Successfully converted PDF with {len(images)} pages to images.")
        return images
    except Exception as e:
        logger.error(f"Failed to convert PDF to images: {e}")
        raise 