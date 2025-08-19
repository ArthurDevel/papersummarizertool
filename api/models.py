from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Column, DateTime, Integer, String, Text, UniqueConstraint, Float

from shared.db import Base


class PaperRow(Base):
    __tablename__ = "papers"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    paper_uuid = Column(String(36), nullable=False)
    arxiv_id = Column(String(64), nullable=False)
    arxiv_version = Column(String(10), nullable=True)
    arxiv_url = Column(String(255), nullable=True)
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

    __table_args__ = (
        UniqueConstraint("paper_uuid", name="uq_papers_paper_uuid"),
        UniqueConstraint("arxiv_id", name="uq_papers_arxiv_id"),
    )


