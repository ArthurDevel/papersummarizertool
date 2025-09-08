from dataclasses import dataclass, field
from typing import List, Optional
import uuid


@dataclass
class ProcessedImage:
    img_base64: str            # base64 string of the image
    page_number: int           # on which page it occurs
    top_left_x: int            # bounding box top-left x coordinate
    top_left_y: int            # bounding box top-left y coordinate
    bottom_right_x: int        # bounding box bottom-right x coordinate
    bottom_right_y: int        # bounding box bottom-right y coordinate
    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))  # uuid4 field, used to reference the image


@dataclass
class Header:
    text: str                  # header text
    level: int                 # header level (1, 2, 3, etc.)
    page_number: int           # which page it appears on
    markdown_line_number: Optional[int] = None  # which line in the OCR markdown (0-based)


@dataclass
class ProcessedPage:
    page_number: int
    img_base64: str             # Base64 encoded page image, max width 1080px
    ocr_markdown: Optional[str] = None      # Raw OCR markdown
    structured_markdown: Optional[str] = None    # With << tags >>
    images: List[ProcessedImage] = field(default_factory=list)     # Images on this page


@dataclass
class ProcessedDocument:
    pdf_base64: str            # base64 encoded version of the pdf
    title: Optional[str] = None
    authors: Optional[str] = None
    pages: List[ProcessedPage] = field(default_factory=list)
    headers: List[Header] = field(default_factory=list)       # Document headers
    final_markdown: Optional[str] = None    # Fully processed output
 