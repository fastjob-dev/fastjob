"""
FastJob: Async Job Queue for Python (Backed by PostgreSQL)
Free Edition - Core job processing functionality

Simple global usage:

    import fastjob
    
    @fastjob.job()
    async def my_job(message: str):
        print(f"Processing: {message}")
    
    await fastjob.enqueue(my_job, message="Hello World")
    await fastjob.run_worker()

Instance-based usage for advanced scenarios:

    app = FastJob(database_url="postgresql://localhost/myapp")
    
    @app.job()
    async def my_job(message: str):
        print(f"Processing: {message}")
    
    await app.enqueue(my_job, message="Hello World")
    await app.run_worker()

FastJob automatically loads Pro/Enterprise plugins when available.
For testing scenarios where you want to disable plugin loading, use:

    from fastjob.testing import disable_plugins, no_plugins

    # Disable plugins for entire test
    disable_plugins()

    # Or use context manager for specific blocks
    with no_plugins():
        # Only core FastJob functionality available
        pass
"""

# FastJob instance-based client
from .client import FastJob

# Type hints
from typing import Optional, Union
from datetime import datetime, timedelta

# Development helpers  
from .settings import is_dev_mode
from .plugins import (
    diagnose_plugins,
    get_plugin_status,
    has_plugin_feature,
)

__version__ = "0.1.0"

# Plugin loading state
_plugins_loaded = False

# Global FastJob instance for convenience API
_global_app: FastJob = None

# Global job registry to survive instance recreation
_global_job_registry = []

# FastJob API exports
__all__ = [
    # Core FastJob class
    "FastJob",
    # Global convenience API
    "job",
    "enqueue", 
    "schedule",
    "run_worker",
    "configure",
    # Job management API
    "get_job_status",
    "cancel_job", 
    "retry_job",
    "delete_job",
    "list_jobs",
    "get_queue_stats",
    # Embedded worker for development
    "start_embedded_worker",
    "stop_embedded_worker", 
    "is_embedded_worker_running",
    "start_embedded_worker_async",
    "stop_embedded_worker_async",
    # Development helpers
    "is_dev_mode", 
    # Plugin system
    "has_plugin_feature",
    "get_plugin_status", 
    "diagnose_plugins",
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
        # Pro/Enterprise imports happen via entry points, not direct imports

        _plugins_loaded = True

    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(f"Plugin loading failed: {e}")
        # Continue with base features only
        _plugins_loaded = True  # Mark as loaded to prevent retry loops


def _get_global_app() -> FastJob:
    """
    Get or create the global FastJob application instance.
    
    This enables a global convenience API.
    The global app is created lazily on first use with default settings.
    If the existing global app is closed, a new one is created automatically.
    """
    global _global_app, _global_job_registry
    
    if _global_app is None or _global_app.is_closed:
        # Create new global app with default settings
        # If previous app was closed, this replaces it
        _global_app = FastJob()
        
        # Re-register all global jobs with the new instance
        for job_func, job_kwargs in _global_job_registry:
            _global_app.job(**job_kwargs)(job_func)
        
    return _global_app


def configure(**kwargs):
    """
    Configure the global FastJob application.
    
    This must be called before using any global functions.
    Similar to other job queues' app.config_from_object().
    
    Args:
        **kwargs: Configuration options to pass to FastJob
        
    Examples:
        import fastjob
        
        fastjob.configure(
            database_url="postgresql://localhost/myapp",
            default_concurrency=8
        )
        
        @fastjob.job()
        async def my_job():
            pass
    """
    global _global_app, _global_job_registry
    
    # Close old global app if it exists and is initialized
    if _global_app is not None and _global_app.is_initialized:
        # Schedule cleanup for the old app (but don't wait for it in sync context)
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if not loop.is_closed():
                loop.create_task(_global_app.close())
        except RuntimeError:
            pass  # No event loop, skip cleanup
    
    # Create new global app with configuration
    _global_app = FastJob(**kwargs)
    
    # Re-register all global jobs with the new instance
    for job_func, job_kwargs in _global_job_registry:
        _global_app.job(**job_kwargs)(job_func)


def job(**kwargs):
    """
    Global job decorator.
    
    Equivalent to app.job() but uses the global FastJob instance.
    Jobs are automatically re-registered if the global instance is recreated.
    
    Args:
        **kwargs: Job configuration options
        
    Examples:
        import fastjob
        
        @fastjob.job(retries=5, queue="urgent")
        async def send_email(to: str, subject: str):
            # send email
            pass
    """
    global _global_job_registry
    
    def decorator(func):
        # Store job info for re-registration if global app is recreated
        _global_job_registry.append((func, kwargs))
        
        # Register with current global app
        app = _get_global_app()
        return app.job(**kwargs)(func)
    
    return decorator


async def enqueue(job_func, **kwargs):
    """
    Enqueue a job using the global FastJob instance.
    
    Args:
        job_func: Job function to enqueue
        **kwargs: Job arguments and options
        
    Returns:
        Job UUID
        
    Examples:
        import fastjob
        
        job_id = await fastjob.enqueue(send_email, to="user@example.com", subject="Hello")
    """
    app = _get_global_app()
    return await app.enqueue(job_func, **kwargs)


async def schedule(
    job_func, 
    *,
    run_at: Optional[datetime] = None,
    run_in: Optional[Union[int, float, timedelta]] = None,
    **kwargs
):
    """
    Schedule a job for future execution using the global FastJob instance.
    
    Args:
        job_func: The job function to schedule  
        run_at: Schedule job at specific datetime (absolute time)
        run_in: Schedule job after delay (relative time - seconds or timedelta)
        **kwargs: Arguments to pass to the job
        
    Returns:
        str: Job UUID
        
    Examples:
        import fastjob
        from datetime import datetime, timedelta
        
        # Schedule at specific datetime (absolute)
        run_time = datetime.now() + timedelta(hours=1)
        job_id = await fastjob.schedule(send_email, run_at=run_time, to="user@example.com")
        
        # Schedule in 1 hour using seconds (relative)
        job_id = await fastjob.schedule(send_email, run_in=3600, to="user@example.com")
        
        # Schedule in 1 hour using timedelta (relative)
        job_id = await fastjob.schedule(send_email, run_in=timedelta(hours=1), to="user@example.com")
    """
    if run_at is None and run_in is None:
        raise ValueError("Must specify either run_at (absolute) or run_in (relative)")
    if run_at is not None and run_in is not None:
        raise ValueError("Cannot specify both run_at and run_in")
        
    if run_in is not None:
        # Convert run_in to absolute time
        if isinstance(run_in, (int, float)):
            run_at = datetime.now() + timedelta(seconds=run_in)
        elif isinstance(run_in, timedelta):
            run_at = datetime.now() + run_in
        else:
            raise ValueError("run_in must be int, float (seconds), or timedelta")
    
    # Use enqueue with scheduled_at to go through the global registry
    return await enqueue(job_func, scheduled_at=run_at, **kwargs)


async def run_worker(
    concurrency: int = 4,
    run_once: bool = False,
    queues: list = None,
):
    """
    Run a worker using the global FastJob instance.
    
    Args:
        concurrency: Number of concurrent job processing tasks
        run_once: If True, process available jobs once and exit
        queues: List of queue names to process. None means all queues.
        
    Examples:
        import fastjob
        
        # Run worker with default settings
        await fastjob.run_worker()
        
        # Run with custom concurrency and specific queues
        await fastjob.run_worker(concurrency=8, queues=["urgent", "default"])
    """
    app = _get_global_app()
    return await app.run_worker(
        concurrency=concurrency,
        run_once=run_once,
        queues=queues
    )


# Job Management API

async def get_job_status(job_id: str):
    """
    Get status information for a specific job.
    
    Args:
        job_id: UUID of the job to check
        
    Returns:
        Dict with job information or None if job not found
        
    Examples:
        import fastjob
        
        job_id = await fastjob.enqueue(my_job, arg="value")
        status = await fastjob.get_job_status(job_id)
        print(f"Job status: {status['status']}")
    """
    app = _get_global_app()
    return await app.get_job_status(job_id)


async def cancel_job(job_id: str):
    """
    Cancel a queued job.
    
    Args:
        job_id: UUID of the job to cancel
        
    Returns:
        True if job was cancelled, False if job wasn't found or already processed
        
    Examples:
        import fastjob
        
        job_id = await fastjob.enqueue(my_job, arg="value")
        cancelled = await fastjob.cancel_job(job_id)
        if cancelled:
            print("Job cancelled successfully")
    """
    app = _get_global_app()
    return await app.cancel_job(job_id)


async def retry_job(job_id: str):
    """
    Retry a failed job.
    
    Args:
        job_id: UUID of the job to retry
        
    Returns:
        True if job was queued for retry, False if job wasn't found or can't be retried
        
    Examples:
        import fastjob
        
        # Retry a failed job
        retried = await fastjob.retry_job(job_id)
        if retried:
            print("Job queued for retry")
    """
    app = _get_global_app()
    return await app.retry_job(job_id)


async def delete_job(job_id: str):
    """
    Delete a job from the queue.
    
    Args:
        job_id: UUID of the job to delete
        
    Returns:
        True if job was deleted, False if job wasn't found
        
    Examples:
        import fastjob
        
        deleted = await fastjob.delete_job(job_id)
        if deleted:
            print("Job deleted successfully")
    """
    app = _get_global_app()
    return await app.delete_job(job_id)


async def list_jobs(
    queue: str = None,
    status: str = None,
    limit: int = 100,
    offset: int = 0
):
    """
    List jobs with optional filtering.
    
    Args:
        queue: Filter by queue name
        status: Filter by job status
        limit: Maximum number of jobs to return
        offset: Number of jobs to skip
        
    Returns:
        List of job dictionaries
        
    Examples:
        import fastjob
        
        # List all jobs
        jobs = await fastjob.list_jobs()
        
        # List failed jobs in specific queue
        failed_jobs = await fastjob.list_jobs(queue="urgent", status="dead_letter")
    """
    app = _get_global_app()
    return await app.list_jobs(queue=queue, status=status, limit=limit, offset=offset)


async def get_queue_stats():
    """
    Get statistics for all queues.
    
    Returns:
        List of dictionaries with queue statistics
        
    Examples:
        import fastjob
        
        stats = await fastjob.get_queue_stats()
        for queue_stats in stats:
            print(f"Queue {queue_stats['queue']}: {queue_stats['queued']} jobs")
    """
    app = _get_global_app()
    return await app.get_queue_stats()


# Import embedded worker functions for development
from .local import (
    start_embedded_worker,
    stop_embedded_worker,
    is_embedded_worker_running,
    start_embedded_worker_async,
    stop_embedded_worker_async,
)
