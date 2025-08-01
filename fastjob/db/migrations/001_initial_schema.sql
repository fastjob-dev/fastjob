-- Migration 001: Initial FastJob schema
-- This creates the core job processing table and indexes

CREATE TABLE IF NOT EXISTS fastjob_jobs (
  id UUID PRIMARY KEY,
  job_name TEXT NOT NULL,
  args JSONB NOT NULL,
  args_hash TEXT, -- Deterministic hash of args for reliable uniqueness
  status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'processing', 'done', 'failed', 'dead_letter', 'cancelled')),
  attempts INT DEFAULT 0,
  max_attempts INT DEFAULT 3,
  queue TEXT DEFAULT 'default',
  priority INT DEFAULT 100,
  unique_job BOOLEAN DEFAULT FALSE,
  scheduled_at TIMESTAMP,
  expires_at TIMESTAMP,
  last_error TEXT,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

-- Performance indexes for job selection
CREATE INDEX IF NOT EXISTS idx_fastjob_jobs_status_priority ON fastjob_jobs (status, priority) WHERE status = 'queued';
CREATE INDEX IF NOT EXISTS idx_fastjob_jobs_queue_status ON fastjob_jobs (queue, status);
CREATE INDEX IF NOT EXISTS idx_fastjob_jobs_scheduled_at ON fastjob_jobs (scheduled_at) WHERE scheduled_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_fastjob_jobs_expires_at ON fastjob_jobs (expires_at) WHERE expires_at IS NOT NULL;

-- Unique constraint for preventing duplicate jobs using deterministic args hash
-- This will be enforced only when unique_job = TRUE and status is 'queued' to allow requeuing after completion
CREATE UNIQUE INDEX IF NOT EXISTS idx_fastjob_jobs_unique_queued 
ON fastjob_jobs (job_name, args_hash) 
WHERE status = 'queued' AND unique_job = TRUE;

-- Index on args_hash for performance
CREATE INDEX IF NOT EXISTS idx_fastjob_jobs_args_hash ON fastjob_jobs (args_hash) WHERE unique_job = TRUE;