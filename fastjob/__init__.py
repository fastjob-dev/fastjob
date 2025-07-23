"""
FastJob: Async Job Queue for Python (Backed by PostgreSQL)
Free Edition - Core job processing functionality
"""

from .core.registry import job
from .core.queue import (
    enqueue, get_job_status, cancel_job, retry_job,
    delete_job, list_jobs, get_queue_stats, schedule
)
from .local import (
    start_embedded_worker, stop_embedded_worker, start_embedded_worker_async,
    is_embedded_worker_running, get_embedded_worker_status
)
from .settings import run_in_dev_mode, is_dev_mode
# Plugin system
from .plugins import discover_and_load_plugins, get_plugin_manager, has_plugin_feature

__version__ = "0.1.0"

# Base functionality always available
__all__ = [
    "job",
    "enqueue",
    "schedule",  # Unified scheduling API
    "get_job_status",
    "cancel_job",
    "retry_job",
    "delete_job",
    "list_jobs",
    "get_queue_stats",
    "start_embedded_worker",
    "stop_embedded_worker",
    "start_embedded_worker_async",
    "is_embedded_worker_running",
    "get_embedded_worker_status",
    # Development helpers
    "run_in_dev_mode",
    "is_dev_mode",
    # Plugin system
    "has_plugin_feature"
]

# Explicit plugin feature loading (replaces magic imports)
def _load_plugin_features():
    """Load plugin features explicitly at import time."""
    try:
        plugin_manager = get_plugin_manager()
        
        # Try to load Pro features if available
        try:
            import fastjob_pro
            # Pro features are already imported in fastjob_pro.__init__.py
            # and accessible via explicit imports: from fastjob_pro import schedule_job
        except ImportError:
            pass
            
        # Try to load Enterprise features if available  
        try:
            import fastjob_enterprise
            # Enterprise features are already imported in fastjob_enterprise.__init__.py
            # and accessible via explicit imports: from fastjob_enterprise import webhook_notify
        except ImportError:
            pass
            
    except Exception:
        # Plugin loading failed, continue with base features only
        pass

# Load plugins at import time (explicit loading instead of magic imports)
discover_and_load_plugins()
_load_plugin_features()