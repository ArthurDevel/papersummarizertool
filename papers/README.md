# Papers Module

This module handles paper storage, retrieval, and management. It provides a clean DTO-based module for working with papers.

## models.py

Contains all Data Transfer Objects (DTOs) used throughout the papers module:

- **Paper** - Main paper DTO containing metadata and full content (pages, sections)
- **Page** - Simple page model with image data
- **Section** - Document section with rewritten content  
- **PaperSlug** - URL-safe paper slug for routing

See [models.py](./models.py) for complete DTO definitions and field details.

**Database Models:** SQLAlchemy models are separate in [db/models.py](./db/models.py) - these handle database persistence while DTOs handle business logic.

## client.py

Main API functions for paper operations:

- `save_paper(db: Session, processed_content: ProcessedDocument) -> Paper` - Save processed document to database and JSON
- `get_paper(db: Session, paper_uuid: str) -> Paper` - Get complete paper with metadata and content loaded from JSON
- `get_paper_metadata(db: Session, paper_uuid: str) -> Paper` - Get paper metadata only (fast, no JSON loading)
- `list_papers(db: Session, statuses: Optional[List[str]], limit: int) -> List[Paper]` - List papers with optional status filtering
- `delete_paper(db: Session, paper_uuid: str) -> bool` - Delete paper and associated files
- `build_paper_slug(title: Optional[str], authors: Optional[str]) -> str` - Generate URL-safe slug from paper metadata

## db/

Database layer responsible for SQLAlchemy operations and transaction management.

- **models.py** - SQLAlchemy models (PaperRecord, PaperSlugRecord)
- **client.py** - Database operations (create, update, get records)

**Transaction Responsibility:** The `db/client.py` layer handles all database commits and transaction management.
