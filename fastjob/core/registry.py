"""
Job Registry System

Instance-based job registration replacing global state patterns.
Supports both instance-based and backward-compatible global operations.
"""

import functools
from typing import Any, Callable, Dict, List, Optional, Type

from pydantic import BaseModel


class JobRegistry:
    """
    Instance-based job registry.

    Manages job registration and lookup for a specific FastJob instance.
    Replaces global _registry pattern with clean instance-based architecture.
    """

    def __init__(self):
        """Initialize empty job registry."""
        self._registry: Dict[str, Dict[str, Any]] = {}

    def register_job(
        self,
        func: Callable[..., Any],
        retries: int = 3,
        args_model: Optional[Type[BaseModel]] = None,
        priority: int = 100,
        queue: str = "default",
        unique: bool = False,
        **kwargs,
    ) -> Callable[..., Any]:
        """
        Register a job function with this registry.

        Args:
            func: Job function to register
            retries: Number of retry attempts (default: 3)
            args_model: Pydantic model for argument validation
            priority: Job priority (lower = higher priority)
            queue: Queue name for job processing
            unique: Whether job should be deduplicated
            **kwargs: Additional job configuration

        Returns:
            The wrapped job function
        """

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        job_name = f"{func.__module__}.{func.__name__}"

        # Store job metadata
        job_config = {
            "func": wrapper,
            "retries": retries,
            "args_model": args_model,
            "priority": priority,
            "queue": queue,
            "unique": unique,
            **kwargs,  # Allow additional configuration
        }

        self._registry[job_name] = job_config

        # Set job metadata on function for introspection
        wrapper._fastjob_name = job_name
        wrapper._fastjob_config = job_config

        return wrapper

    def get_job(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Get job configuration by name.

        Args:
            name: Job name (module.function format)

        Returns:
            Job configuration dict or None if not found
        """
        return self._registry.get(name)

    def get_all_jobs(self) -> List[str]:
        """
        Get all registered job names.

        Returns:
            List of job names
        """
        return list(self._registry.keys())

    def get_jobs_by_queue(self, queue: str) -> List[str]:
        """
        Get all job names for a specific queue.

        Args:
            queue: Queue name

        Returns:
            List of job names in the queue
        """
        return [
            name
            for name, config in self._registry.items()
            if config.get("queue") == queue
        ]

    def clear(self):
        """Clear all registered jobs. Primarily for testing."""
        self._registry.clear()

    def remove_job(self, name: str) -> bool:
        """
        Remove a job from the registry.

        Args:
            name: Job name to remove

        Returns:
            True if job was removed, False if not found
        """
        if name in self._registry:
            del self._registry[name]
            return True
        return False

    def list_jobs(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all jobs with their configurations.

        Returns:
            Dictionary mapping job names to their configurations
        """
        return self._registry.copy()

    def __len__(self) -> int:
        """Get number of registered jobs."""
        return len(self._registry)

    def __contains__(self, name: str) -> bool:
        """Check if job is registered."""
        return name in self._registry


# Global registry for backward compatibility
_global_registry = JobRegistry()


def job(
    retries: int = 3,
    args_model: Optional[Type[BaseModel]] = None,
    priority: int = 100,
    queue: str = "default",
    unique: bool = False,
    **kwargs,
):
    """
    Global job decorator for backward compatibility.

    Uses the global registry instance. For new code, prefer using
    FastJobApp.job() for better isolation and testability.

    Args:
        retries: Number of retry attempts (default: 3)
        args_model: Pydantic model for argument validation
        priority: Job priority (lower = higher priority)
        queue: Queue name for job processing
        unique: Whether job should be deduplicated
        **kwargs: Additional job configuration

    Returns:
        Job decorator function
    """

    def decorator(func: Callable[..., Any]):
        # Ensure plugins are loaded when job is registered
        try:
            from fastjob import _ensure_plugins_loaded

            _ensure_plugins_loaded()
        except ImportError:
            # Handle circular import during initialization
            pass

        return _global_registry.register_job(
            func=func,
            retries=retries,
            args_model=args_model,
            priority=priority,
            queue=queue,
            unique=unique,
            **kwargs,
        )

    return decorator


def get_job(name: str) -> Optional[Dict[str, Any]]:
    """
    Get job from global registry.

    For compatibility, this now delegates to the global FastJob app.

    Args:
        name: Job name

    Returns:
        Job configuration or None
    """
    # Try the new global app first
    try:
        import fastjob

        global_app = fastjob._get_global_app()
        result = global_app.get_job_registry().get_job(name)
        if result is not None:
            return result
    except (ImportError, AttributeError):
        pass

    # Fallback to old global registry
    return _global_registry.get_job(name)


def get_all_jobs() -> List[str]:
    """Get all registered job names from global registry."""
    return _global_registry.get_all_jobs()


def clear_registry():
    """Clear global registry. Used for testing."""
    _global_registry.clear()


def get_global_registry() -> JobRegistry:
    """
    Get the global job registry instance.

    Returns:
        Global JobRegistry instance
    """
    return _global_registry
