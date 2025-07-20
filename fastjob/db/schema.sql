DROP TABLE IF EXISTS fastjob_jobs;

CREATE TABLE fastjob_jobs (
  id UUID PRIMARY KEY,
  job_name TEXT NOT NULL,
  args JSONB NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'done', 'failed', 'dead_letter', 'cancelled')),
  attempts INT DEFAULT 0,
  max_attempts INT DEFAULT 3,
  queue TEXT DEFAULT 'default',
  priority INT DEFAULT 100,
  scheduled_at TIMESTAMP,
  last_error TEXT,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

-- Index for better performance on job selection
CREATE INDEX idx_fastjob_jobs_status_priority ON fastjob_jobs (status, priority) WHERE status = 'queued';
CREATE INDEX idx_fastjob_jobs_queue_status ON fastjob_jobs (queue, status);
CREATE INDEX idx_fastjob_jobs_scheduled_at ON fastjob_jobs (scheduled_at) WHERE scheduled_at IS NOT NULL;

-- Unique constraint for preventing duplicate jobs (job_name + args combination)
-- This will be enforced only when status is 'queued' to allow requeuing after completion
CREATE UNIQUE INDEX idx_fastjob_jobs_unique_queued 
ON fastjob_jobs (job_name, args) 
WHERE status = 'queued';
