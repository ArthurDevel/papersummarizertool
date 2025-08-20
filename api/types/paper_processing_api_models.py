from typing import List, Optional, Dict
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

class UsageModelAggregate(BaseModel):
    num_calls: int
    total_cost: float
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

class UsageSummary(BaseModel):
    currency: str = "USD"
    total_cost: float
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int
    by_model: Dict[str, UsageModelAggregate]

class Paper(BaseModel):
    paper_id: str
    title: Optional[str] = None
    authors: Optional[str] = None
    arxiv_url: Optional[str] = None
    thumbnail_data_url: Optional[str] = None
    sections: List[Section]
    tables: List[Table]
    figures: List[Figure]
    pages: List[Page]
    usage_summary: Optional[UsageSummary] = None
    processing_time_seconds: Optional[float] = None

class JobStatusResponse(BaseModel):
    job_id: str
    status: str 


class MinimalPaperItem(BaseModel):
    paper_uuid: str
    title: Optional[str] = None
    authors: Optional[str] = None
    thumbnail_data_url: Optional[str] = None
    slug: Optional[str] = None