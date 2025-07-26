import importlib
import importlib.util
import os
import pkgutil
import sys
from pathlib import Path


def discover_jobs():
    """
    Discover and import all job modules.

    This function looks for job definitions in:
    1. The module specified by FASTJOB_JOBS_MODULE environment variable (default: "jobs")
    2. A directory with that name in the current working directory
    3. Individual .py files in that directory if module import fails
    """

    # Get the jobs module name from environment variable, default to "jobs"
    jobs_module_name = os.environ.get("FASTJOB_JOBS_MODULE", "jobs")

    # Try the configured jobs module first
    try:
        module = importlib.import_module(jobs_module_name)
        _import_jobs_from_module(module)
        return
    except ImportError:
        pass  # Continue to other discovery methods

    # Try to find the jobs directory in current working directory
    cwd = Path.cwd()
    jobs_dir = cwd / jobs_module_name

    if jobs_dir.exists() and jobs_dir.is_dir():
        # Add the parent directory to Python path temporarily
        if str(cwd) not in sys.path:
            sys.path.insert(0, str(cwd))

        try:
            # Import as a package using the configured module name
            jobs_module = importlib.import_module(jobs_module_name)
            _import_jobs_from_module(jobs_module)
        except ImportError:
            # Try importing individual files
            _import_jobs_from_directory(jobs_dir, jobs_module_name)


def _import_jobs_from_module(module):
    """Import all submodules from a jobs module."""
    try:
        if hasattr(module, "__path__"):
            # It's a package, walk through all submodules
            for _, name, _ in pkgutil.walk_packages(module.__path__):
                importlib.import_module(f".{name}", module.__name__)
        # If it's a single module, it's already imported
    except Exception:
        pass  # Ignore import errors during discovery


def _import_jobs_from_directory(jobs_dir, jobs_module_name):
    """Import Python files from a jobs directory."""
    for py_file in jobs_dir.glob("*.py"):
        if py_file.name.startswith("__"):
            continue  # Skip __init__.py, __pycache__, etc.

        try:
            module_name = f"{jobs_module_name}.{py_file.stem}"
            spec = importlib.util.spec_from_file_location(module_name, py_file)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
        except Exception:
            pass  # Ignore import errors during discovery
