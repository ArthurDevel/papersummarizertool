"""
Migrate existing paper JSON files from filesystem to database.

This script:
1. Only migrates files that don't have processed_content in the database yet
2. On subsequent runs, deletes local files if their content is already in the database
3. Exits early if no local files exist

Usage: python -m migrations.scripts.migrate_json_files_to_db
"""

import os
import json
from sqlalchemy.orm import Session
from shared.db import SessionLocal
from papers.db.models import PaperRecord
from papers.client import get_processed_result_path


### MAIN FUNCTION ###

def migrate_json_files_to_database():
    """
    Read all JSON files from data/paperjsons/ and store in database.
    Deletes local files if they're already in the database.
    """
    # Step 1: Determine the base directory for JSON files
    base_dir = os.path.abspath(os.environ.get("PAPER_JSON_DIR", os.path.join(os.getcwd(), 'data', 'paperjsons')))
    
    # Step 2: Check if directory exists and has JSON files
    if not os.path.exists(base_dir):
        print(f"No JSON directory found at {base_dir}. Nothing to migrate.")
        return
    
    try:
        json_files = [f for f in os.listdir(base_dir) if f.lower().endswith('.json')]
    except Exception as e:
        print(f"Error reading directory {base_dir}: {e}")
        return
    
    if not json_files:
        print("No JSON files found. Nothing to migrate.")
        return
    
    print(f"Found {len(json_files)} JSON files in {base_dir}")
    
    # Step 3: Process each file
    db: Session = SessionLocal()
    
    try:
        migrated_count = 0
        skipped_count = 0
        deleted_count = 0
        error_count = 0
        
        for json_file in json_files:
            # Extract UUID from filename
            paper_uuid = json_file.replace('.json', '')
            json_path = os.path.join(base_dir, json_file)
            
            # Find paper record in database (explicitly load processed_content)
            from sqlalchemy.orm import undefer
            paper = db.query(PaperRecord).options(undefer(PaperRecord.processed_content)).filter(PaperRecord.paper_uuid == paper_uuid).first()
            
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
                json.loads(json_content)
                
                # Store in database
                paper.processed_content = json_content
                db.add(paper)
                
                print(f"Migrated {paper_uuid}")
                migrated_count += 1
                
            except Exception as e:
                print(f"Error migrating {paper_uuid}: {e}")
                error_count += 1
        
        # Step 4: Commit all changes
        if migrated_count > 0:
            db.commit()
            print(f"\nCommitted {migrated_count} migrations to database")
        
        # Step 5: Print summary
        print(f"\nMigration complete:")
        print(f"  Migrated: {migrated_count}")
        print(f"  Deleted (already in DB): {deleted_count}")
        print(f"  Skipped: {skipped_count}")
        print(f"  Errors: {error_count}")
        
    except Exception as e:
        print(f"\nFatal error during migration: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    migrate_json_files_to_database()
