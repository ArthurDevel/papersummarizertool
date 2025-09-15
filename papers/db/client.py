from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from papers.db.models import PaperRecord, PaperSlugRecord


def paper_slug_record_to_paper_slug(record: PaperSlugRecord) -> 'PaperSlug':
    """Convert PaperSlugRecord to PaperSlug DTO."""
    from papers.models import PaperSlug
    return PaperSlug(
        slug=record.slug,
        paper_uuid=record.paper_uuid,
        created_at=record.created_at,
        tombstone=record.tombstone,
        deleted_at=record.deleted_at
    )

def paper_record_to_paper(record: PaperRecord) -> Paper:
    """Convert PaperRecord to Paper DTO."""
    return Paper(
        paper_uuid=record.paper_uuid,
        arxiv_id=record.arxiv_id,
        title=record.title,
        authors=record.authors,
        status=record.status,
        arxiv_version=record.arxiv_version,
        arxiv_url=record.arxiv_url,
        error_message=record.error_message,
        initiated_by_user_id=record.initiated_by_user_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
        started_at=record.started_at,
        finished_at=record.finished_at,
        num_pages=record.num_pages,
        processing_time_seconds=record.processing_time_seconds,
        total_cost=record.total_cost,
        avg_cost_per_page=record.avg_cost_per_page,
        thumbnail_data_url=record.thumbnail_data_url,
    )


def paper_slug_record_to_paper_slug(record: PaperSlugRecord) -> PaperSlug:
    """Convert PaperSlugRecord to PaperSlug DTO."""
    return PaperSlug(
        slug=record.slug,
        paper_uuid=record.paper_uuid,
        created_at=record.created_at,
        tombstone=record.tombstone,
        deleted_at=record.deleted_at,
    )


### DATABASE OPERATIONS ###

def get_paper_record(db: Session, paper_uuid: str) -> PaperRecord:
    """
    Get paper record from database.
    
    Raises:
        FileNotFoundError: If paper not found
    """
    record = db.query(PaperRecord).filter(PaperRecord.paper_uuid == str(paper_uuid)).first()
    if not record:
        raise FileNotFoundError(f"Paper with UUID {paper_uuid} not found")
    return record


def create_paper_record(db: Session, paper: Paper) -> PaperRecord:
    """Create new paper record in database."""
    record = PaperRecord(
        paper_uuid=paper.paper_uuid,
        arxiv_id=paper.arxiv_id,
        title=paper.title,
        authors=paper.authors,
        status=paper.status,
        arxiv_version=paper.arxiv_version,
        arxiv_url=paper.arxiv_url,
        error_message=paper.error_message,
        initiated_by_user_id=paper.initiated_by_user_id,
        created_at=paper.created_at or datetime.utcnow(),
        updated_at=paper.updated_at or datetime.utcnow(),
        started_at=paper.started_at,
        finished_at=paper.finished_at,
        num_pages=paper.num_pages,
        processing_time_seconds=paper.processing_time_seconds,
        total_cost=paper.total_cost,
        avg_cost_per_page=paper.avg_cost_per_page,
        thumbnail_data_url=paper.thumbnail_data_url,
    )
    db.add(record)
    db.commit()
    return record


def update_paper_record(db: Session, paper: Paper) -> PaperRecord:
    """Update existing paper record in database."""
    record = get_paper_record(db, paper.paper_uuid)
    
    record.title = paper.title
    record.authors = paper.authors
    record.status = paper.status
    record.arxiv_version = paper.arxiv_version
    record.arxiv_url = paper.arxiv_url
    record.error_message = paper.error_message
    record.initiated_by_user_id = paper.initiated_by_user_id
    record.updated_at = paper.updated_at or datetime.utcnow()
    record.started_at = paper.started_at
    record.finished_at = paper.finished_at
    record.num_pages = paper.num_pages
    record.processing_time_seconds = paper.processing_time_seconds
    record.total_cost = paper.total_cost
    record.avg_cost_per_page = paper.avg_cost_per_page
    record.thumbnail_data_url = paper.thumbnail_data_url
    
    db.add(record)
    db.commit()
    return record


def list_paper_records(db: Session, statuses: Optional[List[str]], limit: int) -> List[PaperRecord]:
    """List paper records from database."""
    q = db.query(PaperRecord)
    if statuses:
        q = q.filter(PaperRecord.status.in_(statuses))
    q = q.order_by(PaperRecord.created_at.desc()).limit(max(1, min(limit, 1000)))
    return q.all()


def delete_paper_record(db: Session, paper_uuid: str) -> bool:
    """Delete paper record from database."""
    record = db.query(PaperRecord).filter(PaperRecord.paper_uuid == str(paper_uuid)).first()
    if not record:
        return False
    
    db.delete(record)
    db.commit()
    return True


def get_paper_slugs(db: Session, paper_uuid: str) -> List[PaperSlugRecord]:
    """Get all slugs for a paper."""
    return db.query(PaperSlugRecord).filter(PaperSlugRecord.paper_uuid == str(paper_uuid)).all()


def get_all_paper_slugs(db: Session, non_tombstone_only: bool = True) -> List[PaperSlugRecord]:
    """Get all paper slugs, optionally filtering out tombstones."""
    query = db.query(PaperSlugRecord)
    if non_tombstone_only:
        query = query.filter(PaperSlugRecord.tombstone == False)  # noqa: E712
    return query.all()


def tombstone_paper_slugs(db: Session, paper_uuid: str) -> None:
    """Mark all slugs for a paper as tombstoned."""
    from datetime import datetime
    db.query(PaperSlugRecord).filter(
        PaperSlugRecord.paper_uuid == paper_uuid,
        PaperSlugRecord.tombstone == False  # noqa: E712
    ).update({'tombstone': True, 'deleted_at': datetime.utcnow()})
