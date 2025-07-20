
import importlib
import pkgutil
from fastjob.settings import FASTJOB_JOBS_MODULE

def discover_jobs():
    try:
        module = importlib.import_module(FASTJOB_JOBS_MODULE)
        for _, name, _ in pkgutil.walk_packages(module.__path__):
            importlib.import_module(f".{name}", module.__name__)
    except ImportError:
        pass # Module not found, which is fine
