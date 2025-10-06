import sys
import os
import pendulum
from datetime import datetime

from airflow.decorators import dag, task
from sqlalchemy.orm import Session, undefer

# Add project root to Python path to find shared modules
sys.path.insert(0, '/opt/airflow')

from shared.db import SessionLocal
from papers.db.models import PaperRecord


### CONSTANTS ###

# Directory where Airflow stores processed paper JSONs
PAPER_JSON_DIR = os.path.abspath(os.environ.get("PAPER_JSON_DIR", os.path.join(os.getcwd(), 'data', 'paperjsons')))


### HELPER FUNCTIONS ###

def _migrate_json_files_to_database() -> dict:
    """
    Read all JSON files from data/paperjsons/ and store in database.
    Deletes local files if they're already in the database.
    
    Returns:
        dict: Summary of migration results
    """
    # Step 1: Check if directory exists and has JSON files
    if not os.path.exists(PAPER_JSON_DIR):
        print(f"No JSON directory found at {PAPER_JSON_DIR}. Nothing to migrate.")
        return {"migrated": 0, "deleted": 0, "skipped": 0, "errors": 0}
    
    try:
        json_files = [f for f in os.listdir(PAPER_JSON_DIR) if f.lower().endswith('.json')]
    except Exception as e:
        print(f"Error reading directory {PAPER_JSON_DIR}: {e}")
        return {"migrated": 0, "deleted": 0, "skipped": 0, "errors": 1}
    
    if not json_files:
        print("No JSON files found. Nothing to migrate.")
        return {"migrated": 0, "deleted": 0, "skipped": 0, "errors": 0}
    
    print(f"Found {len(json_files)} JSON files in {PAPER_JSON_DIR}")
    
    # Step 2: Process each file
    session: Session = SessionLocal()
    
    try:
        migrated_count = 0
        skipped_count = 0
        deleted_count = 0
        error_count = 0
        
        for json_file in json_files:
            # Extract UUID from filename
            paper_uuid = json_file.replace('.json', '')
            json_path = os.path.join(PAPER_JSON_DIR, json_file)
            
            # Find paper record in database (explicitly load processed_content)
            paper = session.query(PaperRecord).options(undefer(PaperRecord.processed_content)).filter(PaperRecord.paper_uuid == paper_uuid).first()
            
            if not paper:
                print(f"Warning: No database record found for {paper_uuid}, skipping file")
                skipped_count += 1
                continue
            
            # Check if paper already has processed_content
            if paper.processed_content:
                # Content is in database, delete the local file
                try:
                    os.remove(json_path)
                    print(f"Deleted {paper_uuid} - content already in database")
                    deleted_count += 1
                except Exception as e:
                    print(f"Error deleting file {paper_uuid}: {e}")
                    error_count += 1
                continue
            
            # Paper needs migration - read JSON file
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    json_content = f.read()
                
                # Validate JSON
                import json
                json.loads(json_content)
                
                # Store in database
                paper.processed_content = json_content
                session.add(paper)
                
                print(f"Migrated {paper_uuid}")
                migrated_count += 1
                
            except Exception as e:
                print(f"Error migrating {paper_uuid}: {e}")
                error_count += 1
        
        # Step 3: Commit all changes
        if migrated_count > 0:
            session.commit()
            print(f"\nCommitted {migrated_count} migrations to database")
        
        # Step 4: Return summary
        print(f"\nMigration complete:")
        print(f"  Migrated: {migrated_count}")
        print(f"  Deleted (already in DB): {deleted_count}")
        print(f"  Skipped: {skipped_count}")
        print(f"  Errors: {error_count}")
        
        return {
            "migrated": migrated_count,
            "deleted": deleted_count,
            "skipped": skipped_count,
            "errors": error_count
        }
        
    except Exception as e:
        print(f"\nFatal error during migration: {e}")
        session.rollback()
        raise
    finally:
        session.close()


@dag(
    dag_id="migrate_jsons_to_db",
    start_date=pendulum.datetime(2025, 1, 1, tz="UTC"),
    schedule=None,  # Manual trigger only
    catchup=False,
    max_active_runs=1,
    tags=["admin", "migration"],
    doc_md="""
    ### JSON to Database Migration DAG
    
    This DAG migrates paper JSON files from Airflow's filesystem to the database.
    
    **Purpose:**
    - Read JSON files from `/opt/airflow/data/paperjsons/`
    - Store content in database `processed_content` column
    - Delete local files after successful migration
    
    **When to run:**
    - After deploying database-first architecture
    - When Airflow has papers in its volume that aren't in database
    - Can be run multiple times safely (idempotent)
    
    **Trigger manually from Airflow UI**
    """,
)
def migrate_jsons_to_db_dag():
    
    @task
    def migrate_papers() -> dict:
        """
        Migrate all JSON files from Airflow volume to database.
        
        Returns:
            dict: Summary of migration results
        """
        print(f"Starting migration from: {PAPER_JSON_DIR}")
        results = _migrate_json_files_to_database()
        print(f"Migration results: {results}")
        return results
    
    migrate_papers()


migrate_jsons_to_db_dag()
