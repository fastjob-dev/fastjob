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

# Plugin system
from .plugins import discover_and_load_plugins, get_plugin_manager, has_plugin_feature

__version__ = "0.1.0"

# Base functionality always available
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
    "stop_embedded_worker",
    # Plugin system
    "has_plugin_feature"
]

# Plugin feature registry - plugins will register their features here
_plugin_features = {}

def _register_plugin_feature(name: str, func):
    """Register a plugin feature to be available in the fastjob namespace."""
    _plugin_features[name] = func
    # Add to __all__ dynamically
    if name not in __all__:
        __all__.append(name)

def __getattr__(name: str):
    """Dynamic attribute access for plugin features."""
    # Check if it's a registered plugin feature
    if name in _plugin_features:
        return _plugin_features[name]
    
    # Let plugins try to provide the attribute
    plugin_manager = get_plugin_manager()
    
    # Try to get from plugin hooks
    results = plugin_manager.call_hook('get_attribute', name)
    if results:
        # Return the first non-None result
        for result in results:
            if result is not None:
                return result
    
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

def __dir__():
    """Make plugin features visible in dir() for better IDE support."""
    # Get base module attributes
    base_attrs = [attr for attr in globals().keys() if not attr.startswith('_')]
    
    # Add all registered plugin features
    plugin_features = list(_plugin_features.keys())
    
    # Combine and deduplicate
    all_attrs = list(set(base_attrs + plugin_features + __all__))
    
    return sorted(all_attrs)

# Load plugins at import time
discover_and_load_plugins()