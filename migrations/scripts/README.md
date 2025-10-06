# Data Migration Scripts

This directory contains data migration scripts that run automatically on every server startup, after database schema migrations.

## Important Rules

1. **Scripts run on EVERY startup** - These scripts execute automatically via `entrypoint.sh` after `alembic upgrade head`
2. **Must be idempotent** - Scripts should check if work is needed before executing, and be safe to run multiple times
3. **Must handle missing data gracefully** - Exit cleanly if there's nothing to migrate
4. **Should not fail the startup** - Errors are logged but won't prevent the application from starting
5. **File naming** - Use descriptive names (e.g., `migrate_json_files_to_db.py`)

## How It Works

On every server startup, the entrypoint:
1. Runs database schema migrations: `alembic upgrade head`
2. Runs all `.py` files in this directory (except `__init__.py`)
3. Continues to start the application

## Writing a Migration Script

Your script should:
- Check if migration is needed (e.g., check database state, file existence)
- Exit early if nothing to do
- Perform idempotent operations
- Provide clear output of what was done

### Example Structure

```python
"""
Brief description of what this script does.

Usage: Runs automatically on startup via entrypoint.sh
"""

def main():
    # Step 1: Check if migration is needed
    if nothing_to_migrate():
        print("Nothing to migrate. Exiting.")
        return
    
    # Step 2: Perform migration
    # ... your migration logic ...
    
    # Step 3: Report results
    print(f"Migration complete: X items processed")

if __name__ == "__main__":
    main()
```

## Existing Scripts

- `migrate_json_files_to_db.py` - Migrates paper JSON files from filesystem to database `processed_content` column
  - First run: Migrates files that don't have database content yet
  - Second run: Deletes local files that are already in database
  - Subsequent runs: Exits early if no files exist
