"""
FastJob helper functions for common development patterns
"""

from .settings import get_settings


def run_in_dev_mode() -> bool:
    """
    Check if FastJob should run in development mode.
    
    Development mode enables:
    - Embedded worker auto-start
    - Enhanced debugging
    - Local-friendly defaults
    
    Controlled by FASTJOB_DEV_MODE environment variable.
    
    Returns:
        bool: True if in development mode
        
    Examples:
        # In your app startup
        @app.on_event("startup")
        async def startup():
            if fastjob.run_in_dev_mode():
                fastjob.start_embedded_worker()
                
        # Or more explicit
        @app.on_event("startup") 
        async def startup():
            # Development: FASTJOB_DEV_MODE=true
            # Production: FASTJOB_DEV_MODE=false (default)
            if fastjob.run_in_dev_mode():
                fastjob.start_embedded_worker()
    """
    settings = get_settings()
    return settings.dev_mode


def is_dev_mode() -> bool:
    """Alias for run_in_dev_mode() for readability."""
    return run_in_dev_mode()