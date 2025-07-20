import os

FASTJOB_DATABASE_URL = os.environ.get("FASTJOB_DATABASE_URL", "postgresql://postgres@localhost/postgres")
FASTJOB_JOBS_MODULE = os.environ.get("FASTJOB_JOBS_MODULE", "jobs")
