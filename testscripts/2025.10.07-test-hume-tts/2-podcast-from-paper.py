"""
Generate a podcast from a paper in the database.

This script connects to the database, lists available papers,
and allows interactive selection for podcast generation.
"""

import asyncio
import httpx
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from hume import HumeClient
from hume.core.api_error import ApiError
from hume.tts import PostedUtterance, PostedUtteranceVoiceWithId, FormatMp3
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from shared.config import settings
from papers.client import list_minimal_papers
from papers.db.client import get_paper_record
from shared.openrouter.client import get_llm_response

load_dotenv()


### DATA MODELS ###

class PaperSection(BaseModel):
    """Section of a paper with rewritten content."""
    rewritten_content: str
    summary: Optional[str] = None
    subsections: list["PaperSection"] = []
    start_page: Optional[int] = None
    end_page: Optional[int] = None
    level: Optional[int] = None
    section_title: Optional[str] = None


class PaperData(BaseModel):
    """Complete paper data loaded from database JSON."""
    paper_id: str
    title: str
    authors: str
    five_minute_summary: Optional[str] = None
    sections: list[PaperSection]
    num_pages: int
    processing_time_seconds: Optional[float] = None
    total_cost: Optional[float] = None
    avg_cost_per_page: Optional[float] = None


### CONSTANTS ###

OUTPUT_DIR = Path(__file__).parent / "output"
PAPER_JSON_FILENAME = "selected_paper.json"
PODCAST_SCRIPT_FILENAME = "podcast_script.md"
PODCAST_AUDIO_FILENAME = "podcast.mp3"
PROMPT_FILE = Path(__file__).parent / "podcast_generation_prompt.md"
LLM_MODEL = "google/gemini-2.5-flash"
HUME_TIMEOUT_SECONDS = 300.0
MAX_AUDIO_CHARS = 1000

# Voice assignments for podcast hosts (Voice IDs from Hume AI)
HOST_VOICES = {
    "Host 1": "ee96fb5f-ec1a-4f41-a9ba-6d119e64c8fd",
    "Host 2": "9e068547-5ba4-4c8e-8e03-69282a008f04"
}


### DATABASE SETUP ###

def _create_local_database_session():
    """
    Create a database session for local development.
    
    Overrides MYSQL_HOST to use localhost instead of Docker service name.
    
    Returns:
        SQLAlchemy Session: Database session
    """
    # Build connection URL with localhost
    database_url = (
        f"mysql+pymysql://{settings.MYSQL_USER}:{settings.MYSQL_PASSWORD}"
        f"@localhost:{settings.MYSQL_PORT}/{settings.MYSQL_DATABASE}"
    )
    
    # Create engine and session
    engine = create_engine(database_url, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    
    return SessionLocal()


### HELPER FUNCTIONS ###

def _parse_podcast_script(script_path: Path) -> list[tuple[str, str]]:
    """
    Parse podcast script markdown file into dialogue lines.
    
    Args:
        script_path: Path to the podcast script markdown file
        
    Returns:
        list of tuples: [(speaker, text), ...]
        
    Raises:
        FileNotFoundError: If script file not found
        ValueError: If script format is invalid
    """
    if not script_path.exists():
        raise FileNotFoundError(f"Script file not found: {script_path}")
    
    script_text = script_path.read_text(encoding="utf-8")
    
    # Pattern to match: **Speaker Name:** dialogue text
    pattern = r'\*\*(.+?):\*\*\s*(.+?)(?=\n\*\*|\Z)'
    
    matches = re.findall(pattern, script_text, re.DOTALL)
    
    if not matches:
        raise ValueError("Could not parse script. Expected format: **Speaker:** text")
    
    # Clean up the dialogue text
    dialogue_lines = []
    for speaker, text in matches:
        speaker = speaker.strip()
        text = text.strip()
        if text:
            dialogue_lines.append((speaker, text))
    
    return dialogue_lines


def _generate_podcast_audio(script_path: Path) -> None:
    """
    Generate podcast audio from script file using Hume AI TTS.
    
    Args:
        script_path: Path to the podcast script markdown file
        
    Raises:
        ValueError: If HUME_API_KEY not set or script parsing fails
    """
    # Step 1: Get API key
    api_key = os.getenv("HUME_API_KEY")
    if not api_key:
        raise ValueError("HUME_API_KEY environment variable is not set")
    
    # Step 2: Parse script
    print("Parsing podcast script...")
    dialogue_lines = _parse_podcast_script(script_path)
    print(f"Found {len(dialogue_lines)} dialogue lines")
    
    # Step 3: Create utterances with appropriate voices (limited by MAX_AUDIO_CHARS)
    print("Creating utterances with voice assignments...")
    utterances = []
    total_chars = 0
    
    for speaker, text in dialogue_lines:
        # Check if adding this utterance would exceed the character limit
        if total_chars + len(text) > MAX_AUDIO_CHARS:
            print(f"Character limit reached ({MAX_AUDIO_CHARS} chars). Stopping at {len(utterances)} utterances.")
            break
        
        # Get voice ID for speaker, default to first host voice if not found
        voice_id = HOST_VOICES.get(speaker, HOST_VOICES["Host 1"])
        
        utterance = PostedUtterance(
            text=text,
            voice=PostedUtteranceVoiceWithId(
                id=voice_id,
                provider="HUME_AI"
            )
        )
        utterances.append(utterance)
        total_chars += len(text)
    
    print(f"Generating audio for {len(utterances)} utterances ({total_chars} characters)")
    
    # Step 4: Initialize Hume client with extended timeout and synthesize
    print(f"Synthesizing audio with Hume AI...")
    httpx_client = httpx.Client(timeout=HUME_TIMEOUT_SECONDS)
    client = HumeClient(api_key=api_key, httpx_client=httpx_client)
    
    try:
        audio_generator = client.tts.synthesize_file(
            utterances=utterances,
            format=FormatMp3()
        )
        
        # Step 5: Collect audio data
        print("Collecting audio chunks...")
        audio_chunks = []
        for chunk in audio_generator:
            audio_chunks.append(chunk)
        audio_data = b"".join(audio_chunks)
    except ApiError as error:
        # Extract clean error message from Hume API response
        error_message = error.body.get("message", str(error)) if hasattr(error, "body") and isinstance(error.body, dict) else str(error)
        raise RuntimeError(f"Hume AI API error: {error_message}")
    except Exception as error:
        raise RuntimeError(f"Audio synthesis failed: {error}")
    
    # Step 6: Save audio file
    output_path = OUTPUT_DIR / PODCAST_AUDIO_FILENAME
    with open(output_path, "wb") as audio_file:
        audio_file.write(audio_data)
    
    print(f"Podcast audio saved to: {output_path}")
    print(f"File size: {len(audio_data):,} bytes")


async def _generate_podcast_script(paper_data: PaperData) -> str:
    """
    Generate a podcast script from paper data using LLM.
    
    Args:
        paper_data: Paper data with sections
        
    Returns:
        str: Generated podcast script in markdown format
        
    Raises:
        FileNotFoundError: If prompt file not found
        RuntimeError: If LLM call fails
    """
    # Step 1: Read system prompt
    if not PROMPT_FILE.exists():
        raise FileNotFoundError(f"Prompt file not found: {PROMPT_FILE}")
    
    system_prompt = PROMPT_FILE.read_text(encoding="utf-8")
    
    # Step 2: Concatenate all section content
    user_message_parts = [
        f"# {paper_data.title}",
        f"Authors: {paper_data.authors}",
        "",
        "## Paper Content",
        ""
    ]
    
    for section in paper_data.sections:
        if section.section_title:
            user_message_parts.append(f"### {section.section_title}")
        user_message_parts.append(section.rewritten_content)
        user_message_parts.append("")
    
    user_message = "\n".join(user_message_parts)
    
    # Step 3: Call LLM
    print(f"Generating podcast script using {LLM_MODEL}...")
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]
    
    result = await get_llm_response(messages, LLM_MODEL)
    
    if not result.response_text:
        raise RuntimeError("LLM returned empty response")
    
    # Step 4: Print cost info
    if result.cost_info.total_cost:
        print(f"LLM call cost: ${result.cost_info.total_cost:.4f}")
    print(f"Tokens used: {result.cost_info.total_tokens}")
    
    return result.response_text


def _save_paper_json(paper_uuid: str, db_session) -> tuple[Path, PaperData]:
    """
    Fetch paper JSON from database and save to output directory.
    
    Args:
        paper_uuid: UUID of the paper to fetch
        db_session: Database session
        
    Returns:
        tuple: (Path to saved JSON file, PaperData object)
        
    Raises:
        FileNotFoundError: If paper or processed content not found
    """
    # Step 1: Create output directory if it doesn't exist
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    # Step 2: Fetch paper record with processed content
    paper_record = get_paper_record(db_session, paper_uuid, load_content=True)
    
    if not paper_record.processed_content:
        raise FileNotFoundError(f"No processed content found for paper {paper_uuid}")
    
    # Step 3: Parse JSON into DTO
    paper_json = json.loads(paper_record.processed_content)
    paper_data = PaperData.model_validate(paper_json)
    
    # Step 4: Write to file (overwrites if exists)
    output_path = OUTPUT_DIR / PAPER_JSON_FILENAME
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(paper_record.processed_content)
    
    return output_path, paper_data


### MAIN FUNCTIONS ###

def display_papers_menu(papers: list[dict]) -> None:
    """
    Display a numbered list of papers for selection.
    
    Args:
        papers: List of paper dictionaries with uuid, title, authors
    """
    print("\n" + "=" * 80)
    print("AVAILABLE PAPERS")
    print("=" * 80 + "\n")
    
    if not papers:
        print("No completed papers found in the database.")
        return
    
    for idx, paper in enumerate(papers, start=1):
        title = paper.get("title", "Untitled")
        authors = paper.get("authors", "Unknown authors")
        paper_uuid = paper.get("paper_uuid", "")
        
        # Truncate long titles and authors for display
        title_display = title[:70] + "..." if len(title) > 70 else title
        authors_display = authors[:60] + "..." if len(authors) > 60 else authors
        
        print(f"{idx}. {title_display}")
        print(f"   Authors: {authors_display}")
        print(f"   UUID: {paper_uuid}")
        print()


def get_user_selection(papers: list[dict]) -> dict:
    """
    Prompt user to select a paper from the list.
    
    Args:
        papers: List of paper dictionaries
        
    Returns:
        dict: Selected paper dictionary
        
    Raises:
        ValueError: If no papers available or user cancels
    """
    if not papers:
        raise ValueError("No papers available for selection")
    
    while True:
        try:
            print("=" * 80)
            user_input = input(f"Select a paper (1-{len(papers)}) or 'q' to quit: ").strip()
            
            if user_input.lower() == 'q':
                raise ValueError("User cancelled selection")
            
            selection = int(user_input)
            
            if 1 <= selection <= len(papers):
                selected_paper = papers[selection - 1]
                print(f"\nSelected: {selected_paper.get('title', 'Untitled')}")
                return selected_paper
            else:
                print(f"Please enter a number between 1 and {len(papers)}")
                
        except ValueError as error:
            if "User cancelled" in str(error):
                raise
            print("Invalid input. Please enter a valid number or 'q' to quit.")


def run_interactive_paper_selection() -> dict:
    """
    Run the interactive paper selection process.
    
    Connects to database, lists papers, and gets user selection.
    
    Returns:
        dict: Selected paper with uuid, title, authors, etc.
        
    Raises:
        RuntimeError: If database connection fails
        ValueError: If no papers found or user cancels
    """
    print("\nConnecting to database...")
    
    # Step 1: Create database session
    db = _create_local_database_session()
    
    try:
        # Step 2: Fetch completed papers from database
        print("Fetching completed papers...")
        papers = list_minimal_papers(db)
        
        if not papers:
            raise ValueError("No completed papers found in database")
        
        print(f"Found {len(papers)} completed papers")
        
        # Step 3: Display papers and get selection
        display_papers_menu(papers)
        selected_paper = get_user_selection(papers)
        
        return selected_paper
        
    finally:
        db.close()


async def main() -> None:
    """
    Main entry point for the podcast generation script.
    """
    db = None
    
    try:
        # Step 1: Select paper interactively
        selected_paper = run_interactive_paper_selection()
        
        # Step 2: Extract paper details
        paper_uuid = selected_paper["paper_uuid"]
        paper_title = selected_paper.get("title", "Untitled")
        
        print("\n" + "=" * 80)
        print("PODCAST GENERATION")
        print("=" * 80)
        print(f"\nPaper UUID: {paper_uuid}")
        print(f"Title: {paper_title}")
        print()
        
        # Step 3: Fetch and save paper JSON
        print("Fetching paper content from database...")
        db = _create_local_database_session()
        output_path, paper_data = _save_paper_json(paper_uuid, db)
        print(f"Paper JSON saved to: {output_path}")
        print(f"Loaded {len(paper_data.sections)} sections")
        print()
        
        # Step 4: Generate podcast script
        podcast_script = await _generate_podcast_script(paper_data)
        
        # Step 5: Save podcast script
        script_path = OUTPUT_DIR / PODCAST_SCRIPT_FILENAME
        script_path.write_text(podcast_script, encoding="utf-8")
        print(f"\nPodcast script saved to: {script_path}")
        print()
        
        # Step 6: Generate podcast audio
        _generate_podcast_audio(script_path)
        
        print("\n" + "=" * 80)
        print("PODCAST GENERATION COMPLETE")
        print("=" * 80 + "\n")
        
    except ValueError as error:
        print(f"\nOperation cancelled: {error}")
        sys.exit(1)
    except Exception as error:
        print(f"\nError: {error}")
        raise
    finally:
        if db:
            db.close()


if __name__ == "__main__":
    asyncio.run(main())
