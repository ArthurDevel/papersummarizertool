# Airflow Setup for Scheduled Jobs

This document explains how we use Airflow to run scheduled Python scripts and how you can get started.

## 1. How Our Setup Works

Our Airflow setup is designed to be simple and easy for developers to use.

- **DAGs are Jobs:** The core logic for your jobs is written directly in Python files, which are called "DAGs". You can find them in the `dags/` folder.
- **One Place for Dependencies:** All Python packages needed for our jobs (like `requests` or `pandas`) are listed in a single file: `airflow/requirements.txt`. This keeps the environment simple to manage.
- **Docker-Powered:** The entire Airflow system (web server, scheduler, database) runs in Docker, managed by the main `docker-compose.yml` file in the project root.

## 2. Running Locally & Hot-Reloading

Getting Airflow running on your local machine is straightforward.

**To start everything:**
1.  Open your terminal in the project root.
2.  Run the command: `docker-compose up --build`

After a minute, the Airflow web interface will be available at **[http://localhost:8080](http://localhost:8080)**.
- **Username:** `admin`
- **Password:** `admin`

> **Note:** You can change the port by setting the `HOSTPORT_AIRFLOW` variable in your `.env` file (e.g., `HOSTPORT_AIRFLOW=8081`).

**Hot-Reloading is Automatic:**
Thanks to our development setup, you **do not need to restart** anything when you change a DAG file. Just save your changes in any file inside the `dags/` folder, and they will be automatically picked up and reflected in the Airflow UI within a few seconds.

## 3. How to Add a New Job (DAG)

Here’s how to create a new scheduled job.

**Step 1: Create a New Python File**
- In the `airflow/dags/` directory, create a new file. The name should end with `_dag.py` (e.g., `process_reports_dag.py`).

**Step 2: Write Your Job Logic**
- Use the `hello_world_dag.py` file as a template.
- Define the work you want to do inside a Python function.
- Add the `@task` decorator above your function to turn it into an Airflow task.

**Step 3 (If needed): Add Python Packages**
- If your new job needs a Python package that isn't already installed (e.g., `scikit-learn`), add the package name to a new line in the `airflow/requirements.txt` file.

**Step 4 (If needed): Rebuild the Environment**
- You only need to do this if you changed `airflow/requirements.txt`.
- Stop the running services (`Ctrl+C` in the terminal).
- Run `docker-compose up --build` again. This rebuilds the Docker image with your new packages installed.

## 4. Importing Modules from Other Parts of the Codebase

If your DAG needs to import from other modules in the project (like `shared`, `papers`, `users`, etc.), follow these steps:

**Step 1: Add Python Path**
Add this to the top of your DAG file:
```python
import sys
# Add project root to Python path to find shared modules
sys.path.insert(0, '/opt/airflow')
```

**Step 2: Add Required Dependencies**
If the imported modules have dependencies not already in Airflow, add them to `airflow/requirements.txt`:
```
# Example: if importing from shared/config.py
pydantic-settings==2.10.1
python-dotenv==1.0.0
```

**Step 3: Import Normally**
```python
from shared.db import SessionLocal
from papers.client import create_paper
from papers.models import Paper
```

**How It Works:**
- **Development**: Project root is mounted at `/opt/airflow` via `docker-compose.override.yaml`
- **Production**: Modules are copied to `/opt/airflow/` during Docker build via `airflow/Dockerfile`
- The `sys.path.insert(0, '/opt/airflow')` makes Python look in the project root for modules
