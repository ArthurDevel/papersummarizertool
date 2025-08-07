from typing import Dict, Any, Literal
import uuid

JobStatus = Literal["processing", "completed", "failed"]

# In-memory store for job statuses and results
# In a production environment, you would replace this with a more robust
# solution like Redis or a database.
jobs: Dict[str, Dict[str, Any]] = {}

def create_job() -> str:
    """Creates a new job and returns the job ID."""
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "processing", "result": None}
    return job_id

def get_job_status(job_id: str) -> Dict[str, Any] | None:
    """Gets the status and result of a job."""
    return jobs.get(job_id)

def update_job_status(job_id: str, status: JobStatus, result: Any = None):
    """Updates the status and result of a job."""
    if job_id in jobs:
        jobs[job_id]["status"] = status
        jobs[job_id]["result"] = result 