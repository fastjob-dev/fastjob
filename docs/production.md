# Production Deployment Guide

FastJob is designed to be production-ready out of the box. This guide covers deployment patterns, monitoring, and scaling for production environments.

## Quick Production Checklist

- [ ] PostgreSQL configured with connection pooling
- [ ] `FASTJOB_DATABASE_URL` set correctly
- [ ] `FASTJOB_DEV_MODE` unset (should be false/unset in production)
- [ ] Worker processes configured with appropriate concurrency
- [ ] Queue separation for different job types
- [ ] Monitoring and alerting set up
- [ ] Log aggregation configured
- [ ] Process supervision (systemd/supervisor/Docker) configured

## Deployment Patterns

### Single Application Deployment

Perfect for monolithic applications:

```bash
# Your application server
python -m uvicorn main:app --host 0.0.0.0 --port 8000

# FastJob workers (separate processes)
fastjob start --concurrency 4 --queues default,emails,background
```

### Microservices Deployment

Each service manages its own job queue:

```bash
# User Service
fastjob start --database-url="postgresql://localhost/user_service" --concurrency 2 --queues user_tasks

# Order Service  
fastjob start --database-url="postgresql://localhost/order_service" --concurrency 4 --queues order_processing

# Notification Service
fastjob start --database-url="postgresql://localhost/notifications" --concurrency 1 --queues emails,sms
```

### Queue Separation

Separate workers for different job types:

```bash
# High-priority, time-sensitive jobs
fastjob start --queues critical,urgent --concurrency 2

# Normal background jobs
fastjob start --queues default,emails --concurrency 4

# Heavy, long-running jobs
fastjob start --queues heavy,reports --concurrency 1
```

## Systemd Service

### Simple Service File

```ini
# /etc/systemd/system/fastjob-worker.service
[Unit]
Description=FastJob Worker
After=postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=fastjob
Group=fastjob
WorkingDirectory=/opt/myapp
Environment=FASTJOB_DATABASE_URL=postgresql://fastjob:password@localhost/myapp
Environment=FASTJOB_LOG_LEVEL=INFO
Environment=FASTJOB_RESULT_TTL=300
ExecStart=/opt/myapp/venv/bin/fastjob start --concurrency 4
Restart=always
RestartSec=5
KillMode=mixed
TimeoutStopSec=30

# Resource limits
LimitNOFILE=65536
MemoryMax=1G

[Install]
WantedBy=multi-user.target
```

### Multiple Queue Services

```ini
# /etc/systemd/system/fastjob-critical.service
[Unit]
Description=FastJob Critical Worker
After=postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=fastjob
Group=fastjob
WorkingDirectory=/opt/myapp
Environment=FASTJOB_DATABASE_URL=postgresql://fastjob:password@localhost/myapp
ExecStart=/opt/myapp/venv/bin/fastjob start --queues critical,urgent --concurrency 2
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```ini
# /etc/systemd/system/fastjob-background.service
[Unit]
Description=FastJob Background Worker
After=postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=fastjob
Group=fastjob
WorkingDirectory=/opt/myapp
Environment=FASTJOB_DATABASE_URL=postgresql://fastjob:password@localhost/myapp
ExecStart=/opt/myapp/venv/bin/fastjob start --queues default,emails --concurrency 4
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable fastjob-critical fastjob-background
sudo systemctl start fastjob-critical fastjob-background
sudo systemctl status fastjob-*
```

## Docker Deployment

### Basic Dockerfile

```dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Create app user
RUN useradd --create-home --shell /bin/bash fastjob

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Change ownership to app user
RUN chown -R fastjob:fastjob /app

# Switch to app user
USER fastjob

# Default command
CMD ["fastjob", "start", "--concurrency", "4"]
```

### Docker Compose

```yaml
# docker-compose.yml
version: '3.8'

services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: myapp
      POSTGRES_USER: fastjob
      POSTGRES_PASSWORD: password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432"

  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      FASTJOB_DATABASE_URL: postgresql://fastjob:password@postgres/myapp
    depends_on:
      - postgres
    command: python -m uvicorn main:app --host 0.0.0.0 --port 8000

  fastjob-critical:
    build: .
    environment:
      FASTJOB_DATABASE_URL: postgresql://fastjob:password@postgres/myapp
      FASTJOB_LOG_LEVEL: INFO
    depends_on:
      - postgres
    command: fastjob start --queues critical,urgent --concurrency 2
    restart: unless-stopped

  fastjob-background:
    build: .
    environment:
      FASTJOB_DATABASE_URL: postgresql://fastjob:password@postgres/myapp
      FASTJOB_LOG_LEVEL: INFO
    depends_on:
      - postgres
    command: fastjob start --queues default,emails --concurrency 4
    restart: unless-stopped

volumes:
  postgres_data:
```

### Kubernetes Deployment

```yaml
# fastjob-worker.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: fastjob-worker
  labels:
    app: fastjob-worker
spec:
  replicas: 3
  selector:
    matchLabels:
      app: fastjob-worker
  template:
    metadata:
      labels:
        app: fastjob-worker
    spec:
      containers:
      - name: fastjob-worker
        image: myapp:latest
        command: ["fastjob", "start", "--concurrency", "4"]
        env:
        - name: FASTJOB_DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: fastjob-secrets
              key: database-url
        - name: FASTJOB_LOG_LEVEL
          value: "INFO"
        resources:
          requests:
            memory: "256Mi"
            cpu: "100m"
          limits:
            memory: "1Gi"
            cpu: "500m"
        livenessProbe:
          exec:
            command:
            - fastjob
            - status
          initialDelaySeconds: 30
          periodSeconds: 30
        readinessProbe:
          exec:
            command:
            - fastjob
            - status
          initialDelaySeconds: 5
          periodSeconds: 10
```

## Database Configuration

### Connection Pooling

FastJob uses asyncpg with built-in connection pooling. Configure for your load:

```python
# In your app configuration
fastjob.configure(
    database_url="postgresql://user:pass@localhost/db",
    db_pool_min_size=5,    # Minimum connections
    db_pool_max_size=20,   # Maximum connections
)
```

Environment variables:
```bash
export FASTJOB_DB_POOL_MIN_SIZE=5
export FASTJOB_DB_POOL_MAX_SIZE=20
```

### PostgreSQL Configuration

Add to `postgresql.conf`:
```ini
# Connection settings
max_connections = 200
shared_buffers = 256MB
effective_cache_size = 1GB

# Performance settings
checkpoint_completion_target = 0.7
wal_buffers = 16MB
default_statistics_target = 100

# Logging (for monitoring)
log_statement = 'all'
log_duration = on
log_line_prefix = '%t [%p]: [%l-1] user=%u,db=%d '
```

### Database Maintenance

Regular cleanup for high-volume environments:

```sql
-- Clean up old completed jobs (if RESULT_TTL > 0)
DELETE FROM fastjob_jobs 
WHERE status = 'done' 
  AND created_at < NOW() - INTERVAL '1 day';

-- Analyze tables for query performance
ANALYZE fastjob_jobs;
ANALYZE fastjob_migrations;

-- Check table sizes
SELECT 
  schemaname,
  tablename,
  attname,
  n_distinct,
  most_common_vals
FROM pg_stats 
WHERE tablename = 'fastjob_jobs';
```

## Monitoring & Alerting

### Health Checks

```python
# health_check.py
import asyncio
import sys
from fastjob.db.connection import get_pool

async def health_check():
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            result = await conn.fetchval("SELECT 1")
            if result == 1:
                print("OK: Database connection healthy")
                return 0
            else:
                print("ERROR: Database connection failed")
                return 1
    except Exception as e:
        print(f"ERROR: Health check failed: {e}")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(health_check())
    sys.exit(exit_code)
```

Add to your service:
```ini
# In systemd service file
ExecStartPre=/opt/myapp/venv/bin/python /opt/myapp/health_check.py
```

### Monitoring Commands

```bash
# System status
fastjob status --verbose

# Worker monitoring
fastjob workers

# Job statistics
fastjob status --jobs

# Queue stats
fastjob status | grep -E "(Queue|Total|Failed)"
```

### Prometheus Metrics

If using FastJob Pro/Enterprise:

```python
# metrics.py
from prometheus_client import Counter, Histogram, Gauge, start_http_server
import fastjob

# Job metrics
job_total = Counter('fastjob_jobs_total', 'Total jobs processed', ['status', 'queue'])
job_duration = Histogram('fastjob_job_duration_seconds', 'Job processing time', ['queue'])
queue_size = Gauge('fastjob_queue_size', 'Current queue size', ['queue'])

# Collect metrics
async def collect_metrics():
    stats = await fastjob.get_queue_stats()
    for stat in stats:
        queue_size.labels(queue=stat['queue']).set(stat['queued'])

# Start metrics server
start_http_server(8000)
```

### Log Aggregation

Configure structured logging:

```python
# logging_config.py
import logging
import json
from datetime import datetime

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }
        return json.dumps(log_data)

# Configure FastJob logging
logger = logging.getLogger('fastjob')
handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logger.addHandler(handler)
logger.setLevel(logging.INFO)
```

Environment configuration:
```bash
export FASTJOB_LOG_LEVEL=INFO
export FASTJOB_LOG_FORMAT=json  # If your setup supports it
```

## Scaling Patterns

### Horizontal Scaling

Multiple worker processes:
```bash
# Scale by adding more worker processes
fastjob start --concurrency 4 &  # Worker 1
fastjob start --concurrency 4 &  # Worker 2  
fastjob start --concurrency 4 &  # Worker 3
```

### Vertical Scaling

Increase concurrency per worker:
```bash
# More concurrent jobs per worker
fastjob start --concurrency 8
```

### Auto-scaling

Based on queue length:
```bash
#!/bin/bash
# autoscale.sh

QUEUE_SIZE=$(fastjob status | grep "Queued:" | awk '{print $2}')
WORKER_COUNT=$(fastjob workers | grep "Active Workers:" | awk '{print $3}')

if [ "$QUEUE_SIZE" -gt 100 ] && [ "$WORKER_COUNT" -lt 10 ]; then
    echo "Scaling up: Queue size $QUEUE_SIZE, workers $WORKER_COUNT"
    systemctl start fastjob-worker@$(($WORKER_COUNT + 1))
elif [ "$QUEUE_SIZE" -lt 10 ] && [ "$WORKER_COUNT" -gt 2 ]; then
    echo "Scaling down: Queue size $QUEUE_SIZE, workers $WORKER_COUNT"
    systemctl stop fastjob-worker@$WORKER_COUNT
fi
```

### Load Balancing

Distribute jobs across database shards:
```python
import hashlib
import fastjob

# Multiple FastJob instances for different shards
shards = {
    'shard1': FastJob(database_url="postgresql://localhost/shard1"),
    'shard2': FastJob(database_url="postgresql://localhost/shard2"),
    'shard3': FastJob(database_url="postgresql://localhost/shard3"),
}

def get_shard(user_id: int):
    """Route jobs based on user ID"""
    shard_key = f"shard{(user_id % 3) + 1}"
    return shards[shard_key]

# Enqueue to appropriate shard
async def process_user_job(user_id: int, data: dict):
    shard = get_shard(user_id)
    return await shard.enqueue(user_processing_job, user_id=user_id, data=data)
```

## Security

### Database Security

```bash
# Create dedicated FastJob user
sudo -u postgres createuser --no-createdb --no-createrole --no-superuser fastjob
sudo -u postgres psql -c "ALTER USER fastjob PASSWORD 'secure_password';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE myapp TO fastjob;"
```

### Network Security

```bash
# Restrict database access
# In pg_hba.conf:
host    myapp    fastjob    10.0.0.0/24    md5
```

### Environment Variables

Never hardcode secrets:
```bash
# Use secret management
export FASTJOB_DATABASE_URL=$(vault kv get -field=url secret/fastjob)

# Or use Docker secrets
docker service create \
  --secret fastjob-db-url \
  --env FASTJOB_DATABASE_URL_FILE=/run/secrets/fastjob-db-url \
  myapp:latest
```

## Troubleshooting

### Common Issues

**Jobs not processing:**
```bash
# Check worker status
fastjob workers

# Check database connection
fastjob status

# Check logs
journalctl -u fastjob-worker -f
```

**High memory usage:**
```bash
# Check queue sizes
fastjob status --verbose

# Monitor database connections
SELECT count(*) FROM pg_stat_activity WHERE datname = 'myapp';

# Reduce concurrency if needed
fastjob start --concurrency 2
```

**Slow job processing:**
```bash
# Check database performance
SELECT * FROM pg_stat_activity WHERE state = 'active';

# Check for locks
SELECT * FROM pg_locks WHERE NOT granted;

# Monitor job processing times
fastjob status --jobs | head -20
```

### Performance Tuning

**Database optimization:**
```sql
-- Add indexes for common queries
CREATE INDEX CONCURRENTLY idx_fastjob_jobs_status_queue 
ON fastjob_jobs(status, queue);

CREATE INDEX CONCURRENTLY idx_fastjob_jobs_scheduled_at 
ON fastjob_jobs(scheduled_at) WHERE status = 'queued';
```

**Connection pool tuning:**
```bash
# Monitor connection usage
SELECT count(*), state FROM pg_stat_activity GROUP BY state;

# Adjust pool size based on workload
export FASTJOB_DB_POOL_MIN_SIZE=10
export FASTJOB_DB_POOL_MAX_SIZE=30
```

## Backup & Recovery

### Database Backup

```bash
# Regular backups
pg_dump myapp > fastjob_backup_$(date +%Y%m%d_%H%M%S).sql

# Restore
psql myapp < fastjob_backup_20241201_120000.sql
```

### Job Recovery

```python
# Retry failed jobs
failed_jobs = await fastjob.list_jobs(status="failed", limit=100)
for job in failed_jobs:
    await fastjob.retry_job(job["id"])
```

That covers the essentials for production deployment. For more advanced scenarios or specific questions, check the main documentation or open an issue on GitHub.