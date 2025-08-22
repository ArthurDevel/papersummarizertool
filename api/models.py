from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Column, DateTime, Integer, String, Text, UniqueConstraint, Float, Boolean
from sqlalchemy.dialects.mysql import MEDIUMTEXT

from shared.db import Base


class PaperRow(Base):
    __tablename__ = "papers"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    paper_uuid = Column(String(36), nullable=False)
    arxiv_id = Column(String(64), nullable=False)
    arxiv_version = Column(String(10), nullable=True)
    arxiv_url = Column(String(255), nullable=True)
    title = Column(String(512), nullable=True)
    authors = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="not_started")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    # Metrics captured after processing completes
    num_pages = Column(Integer, nullable=True)
    processing_time_seconds = Column(Float, nullable=True)
    total_cost = Column(Float, nullable=True)
    avg_cost_per_page = Column(Float, nullable=True)
    # Base64 data URL of a 400x400 PNG thumbnail cropped from the top square of the first page
    thumbnail_data_url = Column(MEDIUMTEXT, nullable=True)

    __table_args__ = (
        UniqueConstraint("paper_uuid", name="uq_papers_paper_uuid"),
        UniqueConstraint("arxiv_id", name="uq_papers_arxiv_id"),
    )



class RequestedPaperRow(Base):
    __tablename__ = "requested_papers"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    arxiv_id = Column(String(64), nullable=False, unique=True)
    # We intentionally treat versions as the same paper; store canonical base URLs
    arxiv_abs_url = Column(String(255), nullable=False)
    arxiv_pdf_url = Column(String(255), nullable=False)
    request_count = Column(Integer, nullable=False, default=1)
    first_requested_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_requested_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    processed = Column(Boolean, nullable=False, default=False)
    title = Column(String(512), nullable=True)
    authors = Column(Text, nullable=True)
    num_pages = Column(Integer, nullable=True)



class PaperSlugRow(Base):
    __tablename__ = "paper_slugs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    slug = Column(String(255), nullable=False, unique=True)
    paper_uuid = Column(String(36), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    # Tombstone preserves the slug after deletion of the paper
    tombstone = Column(Boolean, nullable=False, default=False)
    deleted_at = Column(DateTime, nullable=True)


class NewPaperNotification(Base):
    __tablename__ = "new_paper_notifications"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    email = Column(String(255), nullable=False)
    arxiv_id = Column(String(255), nullable=False)
    requested_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    notified = Column(Boolean, nullable=False, default=False)
