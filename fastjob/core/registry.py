import functools
from typing import Callable, Any, Type
from pydantic import BaseModel

_registry = {}
_job_registry = _registry  # Alias for backward compatibility

def job(retries: int = 3, args_model: Type[BaseModel] = None, priority: int = 100, queue: str = "default", unique: bool = False):
    def decorator(func: Callable[..., Any]):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        job_name = f"{func.__module__}.{func.__name__}"
        _registry[job_name] = {
            "func": wrapper,
            "retries": retries,
            "args_model": args_model,
            "priority": priority,
            "queue": queue,
            "unique": unique,
        }
        return wrapper
    return decorator

def get_job(name: str):
    return _registry.get(name)

def clear_registry():
    """Clear all registered jobs. Used for testing."""
    global _registry
    _registry.clear()