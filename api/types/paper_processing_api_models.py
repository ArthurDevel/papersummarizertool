from typing import List, Optional
from pydantic import BaseModel

class Page(BaseModel):
    page_number: int
    image_data_url: str

class Figure(BaseModel):
    figure_identifier: str
    location_page: int
    explanation: str
    image_path: str
    image_data_url: str
    referenced_on_pages: List[int]
    bounding_box: List[int]
    page_image_size: List[int]

class Table(BaseModel):
    table_identifier: str
    location_page: int
    explanation: str
    image_path: str
    image_data_url: str
    referenced_on_pages: List[int]
    bounding_box: List[int]
    page_image_size: List[int]

class Section(BaseModel):
    level: int
    section_title: str
    start_page: int
    end_page: int
    rewritten_content: Optional[str] = None
    summary: Optional[str] = None
    subsections: List['Section'] = []

class Paper(BaseModel):
    paper_id: str
    title: str
    sections: List[Section]
    tables: List[Table]
    figures: List[Figure]
    pages: List[Page]

class JobStatusResponse(BaseModel):
    job_id: str
    status: str 