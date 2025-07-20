"""
FastJob: Async Job Queue for Python (Backed by PostgreSQL)
Free Edition - Core job processing functionality
"""

from .core.registry import job
from .core.queue import (
    enqueue, get_job_status, cancel_job, retry_job, 
    delete_job, list_jobs, get_queue_stats, schedule_at, schedule_in
)
from .local import start_embedded_worker, stop_embedded_worker

__version__ = "0.1.0"

__all__ = [
    "job", 
    "enqueue", 
    "get_job_status",
    "cancel_job",
    "retry_job", 
    "delete_job",
    "list_jobs",
    "get_queue_stats",
    "schedule_at",
    "schedule_in",
    "start_embedded_worker", 
    "stop_embedded_worker"
]