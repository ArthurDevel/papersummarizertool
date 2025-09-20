import sys
import pendulum
from datetime import datetime, timedelta
from contextlib import contextmanager
from typing import List

from airflow.decorators import dag, task
from airflow.models.param import Param
from sqlalchemy import text
from sqlalchemy.orm import Session

# Add project root to Python path to find shared modules
sys.path.insert(0, '/opt/airflow')

from shared.db import SessionLocal
from papers.db.models import PaperRecord


### DATABASE HELPERS ###

@contextmanager
def database_session():
    """
    Create a database session with automatic commit/rollback handling.
    
    Yields:
        Session: SQLAlchemy session for database operations
        
    Raises:
        Exception: Any database error that occurs during the transaction
    """
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


### RESET FUNCTIONS ###

def _find_stuck_papers(session: Session, minutes_ago: int) -> List[PaperRecord]:
    """
    Find papers stuck in processing status for longer than specified minutes.
    
    Args:
        session: Active database session
        minutes_ago: How many minutes ago to check (papers older than this get reset)
        
    Returns:
        List[PaperRecord]: Papers that are stuck in processing
    """
    cutoff_time = datetime.utcnow() - timedelta(minutes=minutes_ago)
    
    stuck_papers = session.query(PaperRecord).filter(
        PaperRecord.status == 'processing',
        PaperRecord.started_at < cutoff_time
    ).all()
    
    return stuck_papers


def _reset_paper_to_not_started(session: Session, paper: PaperRecord) -> None:
    """
    Reset a single paper back to not_started status.
    
    Args:
        session: Active database session  
        paper: Paper record to reset
    """
    paper.status = 'not_started'
    paper.started_at = None
    paper.error_message = None
    paper.updated_at = datetime.utcnow()
    session.add(paper)
    
    print(f"Reset paper {paper.id} (arXiv: {paper.arxiv_id}) back to not_started")


@dag(
    dag_id="reset_stuck_papers",
    start_date=pendulum.datetime(2025, 1, 1, tz="UTC"),
    schedule=None,  # Manual trigger only
    catchup=False,
    max_active_runs=1,
    tags=["papers", "maintenance"],
    params={
        "minutes_ago": Param(
            default=30,
            type="integer",
            title="Minutes Ago",
            description="Reset papers that started processing this many minutes ago or earlier (default: 30)",
            minimum=5
        )
    },
    doc_md="""
    ### Reset Stuck Papers DAG
    
    Manual DAG to reset papers stuck in 'processing' status back to 'not_started'.
    
    **Usage:**
    1. Trigger manually from Airflow UI
    2. Set 'minutes_ago' parameter (default: 30 minutes)
    3. Papers processing longer than this time get reset
    
    **What it does:**
    - Finds papers with status='processing' older than specified minutes
    - Resets status to 'not_started'
    - Clears started_at and error_message fields
    - Allows papers to be reprocessed
    
    **Safety:** Only affects papers that have been processing for the specified time or longer.
    """,
)
def reset_stuck_papers_dag():
    
    @task
    def reset_stuck_processing_papers(minutes_ago: int = 30) -> dict:
        """
        Reset papers stuck in processing status back to not_started.
        
        Args:
            minutes_ago: Reset papers that started processing this many minutes ago or earlier
            
        Returns:
            dict: Summary of reset operation
        """
        # Convert to int in case parameter comes as string from Airflow
        minutes_ago = int(minutes_ago)
        
        print(f"Looking for papers stuck in processing for {minutes_ago}+ minutes...")
        
        with database_session() as session:
            # Step 1: Find stuck papers
            stuck_papers = _find_stuck_papers(session, minutes_ago)
            
            if not stuck_papers:
                print("No stuck papers found")
                return {
                    "reset_count": 0,
                    "minutes_threshold": minutes_ago,
                    "message": "No papers were stuck in processing"
                }
            
            # Step 2: Reset each stuck paper
            reset_count = 0
            for paper in stuck_papers:
                _reset_paper_to_not_started(session, paper)
                reset_count += 1
            
            print(f"Reset {reset_count} papers back to not_started status")
            
            return {
                "reset_count": reset_count,
                "minutes_threshold": minutes_ago,
                "message": f"Successfully reset {reset_count} stuck papers"
            }
    
    # Single task with parameter input
    reset_stuck_processing_papers(minutes_ago="{{ params.minutes_ago }}")


reset_stuck_papers_dag()
