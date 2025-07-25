"""
FastJob: Async Job Queue for Python (Backed by PostgreSQL)
Free Edition - Core job processing functionality

FastJob automatically loads Pro/Enterprise plugins when available.
For testing scenarios where you want to disable plugin loading, use:

    from fastjob.testing import disable_plugins, no_plugins
    
    # Disable plugins for entire test
    disable_plugins()
    
    # Or use context manager for specific blocks
    with no_plugins():
        # Only core FastJob functionality available
        pass

This ensures zero-configuration upgrades while maintaining test isolation.
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
from .settings import is_dev_mode, get_settings
# Plugin system (explicit loading required)
from .plugins import get_plugin_manager, has_plugin_feature, get_plugin_status, diagnose_plugins

__version__ = "0.1.0"

# Plugin loading state
_plugins_loaded = False

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
    "is_dev_mode",
    "get_settings",
    # Plugin system (explicit loading)
    "load_plugins",
    "has_plugin_feature",
    "get_plugin_status",
    "diagnose_plugins"
]

def _ensure_plugins_loaded():
    """
    Automatically load plugins unless disabled for testing.
    
    This function is called automatically when FastJob operations are performed.
    It respects the test-specific disable mechanism in fastjob.testing.
    """
    global _plugins_loaded
    
    if _plugins_loaded:
        return
        
    # Check if testing has disabled plugin loading
    try:
        from .testing import is_plugin_loading_disabled
        if is_plugin_loading_disabled():
            return
    except ImportError:
        pass  # testing module not available, proceed normally
    
    # Load plugins automatically
    load_plugins()


def load_plugins():
    """
    Load FastJob plugins.
    
    This function is called automatically when you use FastJob operations,
    unless disabled via fastjob.testing utilities. You can also call it
    explicitly if needed.
    
    Examples:
        import fastjob
        
        # Plugins load automatically on first use
        await fastjob.enqueue(my_job)  # Plugins loaded here
        
        # Or load explicitly if needed
        fastjob.load_plugins()
        
        # Check for plugin features
        if fastjob.has_plugin_feature('dashboard'):
            # Use dashboard features
            pass
    """
    global _plugins_loaded
    
    if _plugins_loaded:
        return
        
    from .plugins import discover_and_load_plugins
    
    try:
        # Load plugins through entry points
        discover_and_load_plugins()
        
        # Load Pro/Enterprise features if available
        try:
            import fastjob_pro
            # Pro features are accessible via explicit imports
        except ImportError:
            pass
            
        try:
            import fastjob_enterprise  
            # Enterprise features are accessible via explicit imports
        except ImportError:
            pass
            
        _plugins_loaded = True
            
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Plugin loading failed: {e}")
        # Continue with base features only
        _plugins_loaded = True  # Mark as loaded to prevent retry loops