import sys
import os
import pendulum
import requests
import re
import json
import time
from airflow.decorators import dag, task
from typing import List, Dict, Any, Optional
from contextlib import contextmanager
from airflow.models import Param

# Add project root to Python path to find shared modules
sys.path.insert(0, '/opt/airflow')

from sqlalchemy.orm import Session
from shared.db import SessionLocal
from papers.models import ExternalPopularitySignal
from papers.client import create_paper


### CONSTANTS ###
ALPHAXIV_API_URL = "https://api.alphaxiv.org/papers/v2/feed"
ALPHAXIV_BASE_URL = "https://www.alphaxiv.org"
PAGE_SIZE = 20  # Number of papers to fetch per page from API
TIME_INTERVAL = "3 Days"  # Time window for hot papers


### HELPER FUNCTIONS ###

def fetch_paper_page_signals(arxiv_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch popularity signals from individual AlphaXiv paper page.

    Extracts data from the JSON-LD script tag on the paper detail page,
    which contains view counts, like counts, and comment counts.

    Args:
        arxiv_id: The arXiv ID (universal_paper_id) of the paper

    Returns:
        Dict with 'views', 'likes', 'comments' or None if fetch fails
    """
    paper_url = f"{ALPHAXIV_BASE_URL}/abs/{arxiv_id}"

    try:
        response = requests.get(paper_url, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"  Warning: Failed to fetch paper page for {arxiv_id}: {e}")
        return None

    # Extract JSON-LD data from the page
    match = re.search(
        r'<script data-alphaxiv-id="json-ld-paper-detail-view" type="application/ld\+json">(.+?)</script>',
        response.text
    )

    if not match:
        print(f"  Warning: Could not find JSON-LD data for {arxiv_id}")
        return None

    try:
        json_ld = json.loads(match.group(1))
    except json.JSONDecodeError as e:
        print(f"  Warning: Failed to parse JSON-LD for {arxiv_id}: {e}")
        return None

    # Extract interaction statistics
    interaction_stats = json_ld.get('interactionStatistic', [])
    views = 0
    likes = 0

    for stat in interaction_stats:
        interaction_type = stat.get('interactionType', {}).get('@type', '')
        count = stat.get('userInteractionCount', 0)

        if interaction_type == 'ViewAction':
            views = count
        elif interaction_type == 'LikeAction':
            likes = count

    comments = json_ld.get('commentCount', 0)

    return {
        'views': views,
        'likes': likes,
        'comments': comments
    }


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


@dag(
    dag_id="daily_alphaxiv_papers",
    start_date=pendulum.datetime(2025, 1, 1, tz="UTC"),
    schedule="0 7 * * *",  # 7 AM daily (1 hour after HuggingFace)
    catchup=False,
    tags=["alphaxiv", "papers"],
    params={
        "time_interval": Param(
            type="string",
            default="3 Days",
            enum=["3 Days", "7 Days", "30 Days", "90 Days"],
            title="Time Interval",
            description="How far back in time to fetch hot papers from AlphaXiv."
        ),
        "max_pages_to_check": Param(
            type="integer",
            default=10,
            title="Max Pages to Check",
            description="Maximum number of pages to fetch from AlphaXiv API before sorting and selecting top papers.",
            minimum=1,
            maximum=50
        ),
        "papers_to_add": Param(
            type="integer",
            default=10,
            title="Number of Papers to Add",
            description="The number of top papers to add to the processing queue.",
            minimum=1,
            maximum=50
        )
    },
    doc_md="""
    ### Daily AlphaXiv Papers DAG

    This DAG fetches hot papers from AlphaXiv and adds the top N papers to the processing queue.
    - Fetches papers sorted by "Hot" ranking from AlphaXiv API
    - Extracts popularity signals (views, likes, comments)
    - Adds top papers to the processing queue for summarization
    - When run on its daily schedule, it fetches papers from the last 3 days.
    - When run manually, you can customize the time interval (3, 7, 30, or 90 days) and number of papers to add.
    """,
)
def daily_alphaxiv_papers_dag():

    @task
    def fetch_hot_papers(time_interval: str, max_pages_to_check: int) -> List[Dict[str, Any]]:
        """
        Fetch hot papers from AlphaXiv API across multiple pages.

        Since the API doesn't return papers in a guaranteed order, we fetch multiple
        pages and will sort them later by popularity metrics.

        Uses PAGE_SIZE constant defined at module level.

        Args:
            time_interval: Time window for fetching hot papers (e.g., "3 Days", "7 Days")
            max_pages_to_check: Maximum number of pages to fetch from the API

        Returns:
            List[Dict[str, Any]]: List of paper data from all fetched pages

        Raises:
            Exception: If API call fails or returns invalid data
        """
        max_pages_to_check = int(max_pages_to_check)
        print(f"Fetching hot papers from AlphaXiv")
        print(f"  Time interval: {time_interval}, Page size: {PAGE_SIZE}")
        print(f"  Max pages to check: {max_pages_to_check}")
        print(f"  API URL: {ALPHAXIV_API_URL}")

        all_papers = []
        page_num = 1

        while page_num <= max_pages_to_check:
            params = {
                "pageNum": page_num,
                "sortBy": "Hot",
                "pageSize": PAGE_SIZE,
                "interval": time_interval
            }

            print(f"Fetching page {page_num}/{max_pages_to_check}...")

            try:
                response = requests.get(ALPHAXIV_API_URL, params=params, timeout=30)
                response.raise_for_status()
            except requests.exceptions.RequestException as e:
                raise Exception(f"Failed to fetch papers from AlphaXiv API (page {page_num}): {e}")

            try:
                response_data = response.json()
            except ValueError as e:
                raise Exception(f"Invalid JSON response from AlphaXiv API (page {page_num}): {e}")

            # Extract papers array from response
            papers_on_page = response_data.get('papers', [])

            # If no papers on this page, we've reached the end
            if not papers_on_page:
                print(f"No papers found on page {page_num}, stopping pagination")
                break

            all_papers.extend(papers_on_page)
            print(f"  Fetched {len(papers_on_page)} papers from page {page_num} (total so far: {len(all_papers)})")

            page_num += 1

            # Rate limit: wait 1 second before next API call (unless we're done)
            if page_num <= max_pages_to_check and papers_on_page:
                time.sleep(1)

        if not all_papers:
            print(f"No papers found in AlphaXiv response")
            return []  # Return empty list to allow DAG to complete gracefully

        print(f"\nSuccessfully fetched {len(all_papers)} total papers from {page_num - 1} page(s)")

        # Sort papers by popularity metrics (views, likes, public votes)
        # Prioritize: public_total_votes > likes > views
        def get_popularity_score(paper: Dict[str, Any]) -> tuple:
            metrics = paper.get('metrics', {})
            public_votes = metrics.get('public_total_votes', 0)
            visits = metrics.get('visits_count', {})
            views = visits.get('all', 0) if isinstance(visits, dict) else 0

            # Get likes from the paper page (we'll fetch these later, for now use 0)
            # For sorting purposes, we'll use public_votes as primary metric
            return (public_votes, views)

        sorted_papers = sorted(all_papers, key=get_popularity_score, reverse=True)
        print(f"Sorted {len(sorted_papers)} papers by popularity (public_votes, views)")

        return sorted_papers

    @task
    def print_papers_info(papers_data: List[Dict[str, Any]], papers_to_add: int) -> None:
        """
        Print paper titles and rankings to console.
        Note: Detailed signals (views, likes, comments) are fetched later
        when adding papers to the queue.

        Args:
            papers_data: List of paper data from the API (already sorted by popularity)
            papers_to_add: Number of top papers to display and add

        Raises:
            Exception: If papers_data is empty or malformed
        """
        if not papers_data:
            raise Exception("No papers to display - papers_data is empty")

        papers_to_add = int(papers_to_add)

        # Only display the top N papers that will be added
        papers_to_display = papers_data[:papers_to_add]

        print(f"\n=== AlphaXiv Hot Papers - Top {len(papers_to_display)} (from {len(papers_data)} fetched) ===\n")

        # Print each paper with ranking
        for rank, paper in enumerate(papers_to_display, 1):
            try:
                title = paper.get('title', 'Unknown Title')
                arxiv_id = paper.get('universal_paper_id', 'Unknown')
                metrics = paper.get('metrics', {})
                public_votes = metrics.get('public_total_votes', 0)
                visits = metrics.get('visits_count', {})
                views = visits.get('all', 0) if isinstance(visits, dict) else 0

                # Construct URLs
                arxiv_url = f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id != 'Unknown' else 'N/A'
                alphaxiv_url = f"{ALPHAXIV_BASE_URL}/abs/{arxiv_id}" if arxiv_id != 'Unknown' else 'N/A'

                print(f"#{rank} - {title}")
                print(f"     ArXiv ID: {arxiv_id}")
                print(f"     Public Votes: {public_votes} | Views: {views}")
                print(f"     ArXiv URL: {arxiv_url}")
                print(f"     AlphaXiv URL: {alphaxiv_url}")
                print("")  # Empty line for readability

            except Exception as e:
                print(f"Error processing paper at rank {rank}: {e}")
                print(f"Paper data: {paper}")

        print(f"\n=== End of AlphaXiv Hot Papers ===\n")

    @task
    def add_top_papers_to_queue(papers_data: List[Dict[str, Any]], papers_to_add: int) -> None:
        """
        Add top N papers to processing queue with popularity signals.

        Args:
            papers_data: List of paper data from the API
            papers_to_add: The number of top papers to add to the queue.

        Raises:
            Exception: If database operations fail
        """
        if not papers_data:
            print("No papers to add to queue")
            return

        papers_to_add = int(papers_to_add)

        with database_session() as session:
            added_count = 0
            skipped_count = 0

            for rank, paper in enumerate(papers_data[:papers_to_add], 1):
                try:
                    arxiv_id = paper.get('universal_paper_id')

                    if not arxiv_id:
                        print(f"Skipping paper at rank {rank} - no ArXiv ID")
                        skipped_count += 1
                        continue

                    # Step 1: Extract author information
                    # AlphaXiv doesn't provide authors in the feed, so we'll extract from abstract or leave blank
                    # For now, we'll use None and let it be filled in later during processing
                    authors_str = None
                    title = paper.get('title')

                    if not title:
                        print(f"Skipping {arxiv_id} - no title found")
                        skipped_count += 1
                        continue

                    # Step 2: Fetch popularity signals from the individual paper page
                    print(f"  Fetching signals from paper page...")
                    page_signals = fetch_paper_page_signals(arxiv_id)

                    if not page_signals:
                        print(f"  Warning: Could not fetch page signals for {arxiv_id}, skipping")
                        skipped_count += 1
                        continue

                    # Create popularity signal with data from paper page
                    alphaxiv_signal = ExternalPopularitySignal(
                        source="AlphaXiv",
                        values={
                            "views": page_signals['views'],
                            "likes": page_signals['likes'],
                            "comments": page_signals['comments']
                        },
                        fetch_info={
                            "alphaxiv_paper_id": paper.get('id'),
                            "paper_group_id": paper.get('paper_group_id'),
                            "alphaxiv_url": f"{ALPHAXIV_BASE_URL}/abs/{arxiv_id}"
                        }
                    )

                    # Step 3: Add paper to processing queue
                    create_paper(
                        db=session,
                        arxiv_id=arxiv_id,
                        title=title,
                        authors=authors_str,
                        external_popularity_signals=[alphaxiv_signal],
                        initiated_by_user_id=None  # System job
                    )

                    added_count += 1
                    print(f"Added {arxiv_id} to queue (rank #{rank})")
                    print(f"  Title: {title[:80]}...")
                    print(f"  Views: {page_signals['views']} | Likes: {page_signals['likes']} | Comments: {page_signals['comments']}")

                except ValueError as e:
                    # Paper already exists - this is expected and not an error
                    if "already exists" in str(e):
                        print(f"Skipping {arxiv_id} - already exists in database")
                        skipped_count += 1
                    else:
                        print(f"Error with paper at rank {rank}: {e}")
                        skipped_count += 1
                    continue

                except Exception as e:
                    print(f"Unexpected error adding paper at rank {rank}: {e}")
                    skipped_count += 1
                    continue

            print(f"\n=== Processing Queue Summary ===")
            print(f"Added: {added_count} papers")
            print(f"Skipped: {skipped_count} papers")
            print(f"===========================\n")

    # Define task dependencies
    interval = "{{ params.time_interval }}"
    max_pages = "{{ params.max_pages_to_check }}"
    num_papers = "{{ params.papers_to_add }}"

    papers = fetch_hot_papers(time_interval=interval, max_pages_to_check=max_pages)
    print_papers_info(papers, papers_to_add=num_papers)
    add_top_papers_to_queue(papers, papers_to_add=num_papers)


daily_alphaxiv_papers_dag()
