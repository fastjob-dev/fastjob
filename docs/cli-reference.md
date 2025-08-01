# FastJob CLI Reference

All FastJob CLI commands, including Global and Instance API patterns with the `--database-url` parameter.

## Quick Reference

```bash
# Global API (uses FASTJOB_DATABASE_URL environment variable)
fastjob <command> [options]

# Instance API (specify database URL directly)
fastjob <command> --database-url="postgresql://localhost/service_db" [options]
```

---

## Core Commands

### `fastjob setup`

Initialize FastJob database schema.

```bash
# Global API setup
fastjob setup

# Instance API setup (microservices)
fastjob setup --database-url="postgresql://localhost/user_service"
fastjob setup --database-url="postgresql://localhost/payment_service"
fastjob setup --database-url="postgresql://localhost/notification_service"

# Multi-tenant setup
fastjob setup --database-url="postgresql://localhost/tenant_a_jobs"
fastjob setup --database-url="postgresql://localhost/tenant_b_jobs"
```

**Options:**
- `--database-url TEXT`: PostgreSQL database URL (overrides FASTJOB_DATABASE_URL)
- `--help`: Show help message

**Examples:**
```bash
# Development setup
fastjob setup --database-url="postgresql://localhost/fastjob_dev"

# Production setup with credentials
fastjob setup --database-url="postgresql://user:pass@prod-db:5432/jobs"

# SSL-enabled production setup
fastjob setup --database-url="postgresql://user:pass@prod-db:5432/jobs?sslmode=require"
```

---

### `fastjob migrate`

Apply database migrations. Alias for `setup` for backwards compatibility.

```bash
# Global API
fastjob migrate

# Instance API  
fastjob migrate --database-url="postgresql://localhost/service_db"
```

---

### `fastjob migrate-status`

Show current migration status.

```bash
# Global API
fastjob migrate-status

# Instance API
fastjob migrate-status --database-url="postgresql://localhost/user_service"
```

**Output Example:**
```
Database: postgresql://localhost/user_service
Applied migrations:
  ✅ 001_initial_schema.sql
  ✅ 002_worker_heartbeat.sql
Database is up to date.
```

---

### `fastjob worker` / `fastjob start`

Start job worker processes.

```bash
# Global API worker
fastjob worker --concurrency 4

# Instance API workers (one per service)
fastjob worker --database-url="postgresql://localhost/user_service" --concurrency 2
fastjob worker --database-url="postgresql://localhost/payment_service" --concurrency 1
fastjob worker --database-url="postgresql://localhost/notification_service" --concurrency 4
```

**Options:**
- `--database-url TEXT`: PostgreSQL database URL
- `--concurrency INTEGER`: Number of concurrent workers (default: 1)
- `--queues TEXT`: Comma-separated list of queues to process
- `--run-once`: Process jobs once and exit (useful for testing)
- `--help`: Show help message

**Production Examples:**
```bash
# High-throughput notification service
fastjob worker \
  --database-url="postgresql://localhost/notification_service" \
  --concurrency 8 \
  --queues="email,sms,push"

# Critical payment processing (single worker for safety)
fastjob worker \
  --database-url="postgresql://localhost/payment_service" \
  --concurrency 1 \
  --queues="transactions,refunds"

# Background analytics processing
fastjob worker \
  --database-url="postgresql://localhost/analytics_service" \
  --concurrency 4 \
  --queues="events,reports"
```

---

### `fastjob status`

Show queue and job statistics.

```bash
# Global API status
fastjob status

# Instance API status
fastjob status --database-url="postgresql://localhost/user_service"
```

**Output Example:**
```
Database: postgresql://localhost/user_service
Queue Statistics:
  signups: 5 pending, 127 completed, 2 failed
  profile_updates: 0 pending, 45 completed, 0 failed
  workflows: 2 pending, 23 completed, 1 failed

Total: 7 pending, 195 completed, 3 failed
Success rate: 98.5%
```

---

### `fastjob workers`

List active workers and their status.

```bash
# Global API workers
fastjob workers

# Instance API workers
fastjob workers --database-url="postgresql://localhost/payment_service"
```

**Output Example:**
```
Database: postgresql://localhost/payment_service
Active Workers:
  worker-001: processing (started 2h ago)
  worker-002: idle (started 2h ago)

Total: 2 workers active
```

---

### `fastjob health`

Check system health status.

```bash
# Global API health check
fastjob health

# Instance API health check
fastjob health --database-url="postgresql://localhost/analytics_service"
```

**Options:**
- `--database-url TEXT`: PostgreSQL database URL
- `--verbose`: Show detailed health information
- `--help`: Show help message

**Output Example:**
```
Health Status: HEALTHY

Database: ✅ Connected (10ms)
Job Processing: ✅ 45 jobs processed in last hour
System Resources: ✅ CPU: 15%, Memory: 45%, Disk: 67%

All systems operational.
```

---

### `fastjob ready`

Check if system is ready (readiness probe for containers).

```bash
# Global API readiness
fastjob ready

# Instance API readiness
fastjob ready --database-url="postgresql://localhost/user_service"
```

**Exit Codes:**
- `0`: System ready
- `1`: System not ready

---

## FastJob Pro Commands

### `fastjob dashboard`

Launch web dashboard (requires `pip install fastjob-pro`).

```bash
# Global API dashboard
fastjob dashboard

# Instance API dashboards (multiple services)
fastjob dashboard --database-url="postgresql://localhost/user_service" --port 6161
fastjob dashboard --database-url="postgresql://localhost/payment_service" --port 6162  
fastjob dashboard --database-url="postgresql://localhost/notification_service" --port 6163
```

**Options:**
- `--database-url TEXT`: PostgreSQL database URL
- `--port INTEGER`: Port to run dashboard on (default: 6161)
- `--host TEXT`: Host to bind to (default: localhost)
- `--help`: Show help message

**Microservices Dashboard Setup:**
```bash
# Monitor all services from different ports  
fastjob dashboard --database-url=$USER_SERVICE_DB --port 6161 &
fastjob dashboard --database-url=$PAYMENT_SERVICE_DB --port 6162 &
fastjob dashboard --database-url=$NOTIFICATION_SERVICE_DB --port 6163 &

# Access dashboards:
# User Service: http://localhost:6161
# Payment Service: http://localhost:6162  
# Notification Service: http://localhost:6163
```

---

### `fastjob scheduler`

Start recurring job scheduler (requires `pip install fastjob-pro`).

```bash
# Global API scheduler
fastjob scheduler

# Instance API schedulers
fastjob scheduler --database-url="postgresql://localhost/user_service"
fastjob scheduler --database-url="postgresql://localhost/analytics_service"
```

**Options:**
- `--database-url TEXT`: PostgreSQL database URL
- `--help`: Show help message

---

## FastJob Enterprise Commands

### `fastjob metrics`

Show performance metrics (requires `pip install fastjob-enterprise`).

```bash
# Global API metrics
fastjob metrics

# Instance API metrics (per service)
fastjob metrics --database-url="postgresql://localhost/payment_service"
```

**Options:**
- `--database-url TEXT`: PostgreSQL database URL
- `--format TEXT`: Output format (json, table, csv)
- `--hours INTEGER`: Hours of data to include (default: 24)
- `--help`: Show help message

**Output Example:**
```
Performance Metrics (Last 24 Hours)
Database: postgresql://localhost/payment_service

Jobs Processed: 1,247
Success Rate: 99.2%
Average Duration: 156ms
95th Percentile: 450ms
Peak Throughput: 45 jobs/minute

Top Queues:
- transactions: 890 jobs (71.4%)
- refunds: 234 jobs (18.8%)  
- invoicing: 123 jobs (9.8%)
```

---

### `fastjob dead-letter`

Manage dead letter queue (requires `pip install fastjob-enterprise`).

```bash
# Global API dead letter management
fastjob dead-letter list
fastjob dead-letter requeue --job-id abc123

# Instance API dead letter management
fastjob dead-letter list --database-url="postgresql://localhost/payment_service"
fastjob dead-letter requeue --database-url="postgresql://localhost/payment_service" --job-id def456
```

**Commands:**
- `list`: Show dead letter jobs
- `requeue`: Requeue a dead letter job
- `delete`: Delete a dead letter job
- `stats`: Show dead letter statistics

**Options:**
- `--database-url TEXT`: PostgreSQL database URL
- `--job-id TEXT`: Specific job ID to operate on
- `--limit INTEGER`: Number of jobs to show
- `--help`: Show help message

---

## Environment Variables

### Global API Configuration

```bash
# Required for Global API
export FASTJOB_DATABASE_URL="postgresql://user:password@localhost/fastjob"

# Optional settings
export FASTJOB_DEV_MODE="true"                    # Enable development mode
export FASTJOB_LOG_LEVEL="INFO"                   # Logging level
export FASTJOB_MAX_CONNECTIONS="20"               # Max database connections
export FASTJOB_WORKER_TIMEOUT="300"               # Worker timeout in seconds
```

### Instance API Configuration

```bash
# Service-specific database URLs
export USER_SERVICE_DATABASE_URL="postgresql://localhost/user_service"
export PAYMENT_SERVICE_DATABASE_URL="postgresql://localhost/payment_service"
export NOTIFICATION_SERVICE_DATABASE_URL="postgresql://localhost/notification_service"

# Multi-tenant database URLs
export TENANT_A_DATABASE_URL="postgresql://localhost/tenant_a_jobs"
export TENANT_B_DATABASE_URL="postgresql://localhost/tenant_b_jobs"

# Environment-specific configuration
export ENVIRONMENT="production"
export DATABASE_SSL_MODE="require"
```

---

## Production Deployment Patterns

### Single Service (Global API)

```bash
#!/bin/bash
# Global API production deployment

# Setup
export FASTJOB_DATABASE_URL="postgresql://user:pass@prod-db:5432/jobs"
fastjob setup

# Start workers
fastjob worker --concurrency 8 --queues="high,normal,low" &

# Start dashboard (Pro)
fastjob dashboard --port 8080 &

# Start scheduler (Pro)  
fastjob scheduler &

# Health monitoring
while true; do
  fastjob health || alert "FastJob health check failed"
  sleep 60
done
```

### Microservices (Instance API)

```bash
#!/bin/bash
# Microservices production deployment

# Service databases
USER_DB="postgresql://user:pass@user-db:5432/jobs"
PAYMENT_DB="postgresql://user:pass@payment-db:5432/jobs"
NOTIFICATION_DB="postgresql://user:pass@notification-db:5432/jobs"

# Setup all services
fastjob setup --database-url="$USER_DB"
fastjob setup --database-url="$PAYMENT_DB"
fastjob setup --database-url="$NOTIFICATION_DB"

# Start service-specific workers
fastjob worker --database-url="$USER_DB" --concurrency 4 &
fastjob worker --database-url="$PAYMENT_DB" --concurrency 2 &
fastjob worker --database-url="$NOTIFICATION_DB" --concurrency 8 &

# Start service-specific dashboards (Pro)
fastjob dashboard --database-url="$USER_DB" --port 6161 &
fastjob dashboard --database-url="$PAYMENT_DB" --port 6162 &
fastjob dashboard --database-url="$NOTIFICATION_DB" --port 6163 &

# Start schedulers (Pro)
fastjob scheduler --database-url="$USER_DB" &
fastjob scheduler --database-url="$NOTIFICATION_DB" &

# Health monitoring per service
monitor_service() {
  local db_url=$1
  local service_name=$2
  
  while true; do
    fastjob health --database-url="$db_url" || \
      alert "$service_name health check failed"
    sleep 60
  done
}

monitor_service "$USER_DB" "User Service" &
monitor_service "$PAYMENT_DB" "Payment Service" &
monitor_service "$NOTIFICATION_DB" "Notification Service" &
```

### Multi-Tenant (Instance API)

```bash
#!/bin/bash
# Multi-tenant production deployment

# Tenant-specific setup
for tenant in tenant_a tenant_b tenant_c; do
  db_url="postgresql://user:pass@${tenant}-db:5432/jobs"
  
  # Setup tenant database
  fastjob setup --database-url="$db_url"
  
  # Start tenant-specific worker
  fastjob worker --database-url="$db_url" --concurrency 4 &
  
  # Start tenant-specific dashboard (Pro)
  port=$((6160 + $(echo "$tenant" | tr -d 'a-z' | tr -d '_')))
  fastjob dashboard --database-url="$db_url" --port "$port" &
  
  # Health monitoring per tenant
  monitor_tenant "$db_url" "$tenant" &
done
```

---

## Container Deployment

### Docker Compose (Global API)

```yaml
version: '3.8'

services:
  fastjob-worker:
    image: your-app:latest
    command: ["fastjob", "worker", "--concurrency", "4"]
    environment:
      - FASTJOB_DATABASE_URL=postgresql://user:password@db:5432/jobs
    depends_on:
      - db
    restart: unless-stopped

  fastjob-dashboard:
    image: your-app:latest  
    command: ["fastjob", "dashboard", "--host", "0.0.0.0", "--port", "8080"]
    environment:
      - FASTJOB_DATABASE_URL=postgresql://user:password@db:5432/jobs
    ports:
      - "8080:8080"
    depends_on:
      - db
    restart: unless-stopped

  db:
    image: postgres:15
    environment:
      - POSTGRES_DB=jobs
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped

volumes:
  postgres_data:
```

### Kubernetes (Instance API)

```yaml
# User Service Worker
apiVersion: apps/v1
kind: Deployment
metadata:
  name: user-service-worker
spec:
  replicas: 2
  selector:
    matchLabels:
      app: user-service-worker
  template:
    metadata:
      labels:
        app: user-service-worker
    spec:
      containers:
      - name: worker
        image: your-app:latest
        command: ["fastjob", "worker", "--concurrency", "4"]
        env:
        - name: USER_SERVICE_DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: database-secrets
              key: user-service-url
        args: ["--database-url", "$(USER_SERVICE_DATABASE_URL)"]
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        readinessProbe:
          exec:
            command: ["fastjob", "ready", "--database-url", "$(USER_SERVICE_DATABASE_URL)"]
          initialDelaySeconds: 5
          periodSeconds: 10
        livenessProbe:
          exec:
            command: ["fastjob", "health", "--database-url", "$(USER_SERVICE_DATABASE_URL)"]
          initialDelaySeconds: 30
          periodSeconds: 30

---
# Payment Service Worker  
apiVersion: apps/v1
kind: Deployment
metadata:
  name: payment-service-worker
spec:
  replicas: 1  # Single worker for payment safety
  selector:
    matchLabels:
      app: payment-service-worker
  template:
    metadata:
      labels:
        app: payment-service-worker
    spec:
      containers:
      - name: worker
        image: your-app:latest
        command: ["fastjob", "worker", "--concurrency", "1"]
        env:
        - name: PAYMENT_SERVICE_DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: database-secrets
              key: payment-service-url
        args: ["--database-url", "$(PAYMENT_SERVICE_DATABASE_URL)"]
```

---

## Troubleshooting

### Common Issues

**1. Database Connection Errors**
```bash
# Test database connectivity
fastjob health --database-url="postgresql://localhost/service_db"

# Check migrations
fastjob migrate-status --database-url="postgresql://localhost/service_db"
```

**2. Worker Not Processing Jobs**
```bash
# Check worker status
fastjob workers --database-url="postgresql://localhost/service_db"

# Check queue statistics
fastjob status --database-url="postgresql://localhost/service_db"

# Test with single job processing
fastjob worker --database-url="postgresql://localhost/service_db" --run-once
```

**3. Cross-Service Communication Issues**
```bash
# Verify each service database is accessible
fastjob health --database-url="$USER_SERVICE_DB"
fastjob health --database-url="$PAYMENT_SERVICE_DB"  
fastjob health --database-url="$NOTIFICATION_SERVICE_DB"

# Check service-specific job queues
fastjob status --database-url="$USER_SERVICE_DB"
fastjob status --database-url="$PAYMENT_SERVICE_DB"
fastjob status --database-url="$NOTIFICATION_SERVICE_DB"
```

### Debug Mode

Enable verbose logging for all commands:

```bash
# Add --verbose to any command for detailed output
fastjob health --database-url="postgresql://localhost/service_db" --verbose
fastjob worker --database-url="postgresql://localhost/service_db" --verbose
```

### Performance Monitoring

```bash
# Monitor job processing performance
watch -n 5 'fastjob status --database-url="postgresql://localhost/service_db"'

# Monitor system health
watch -n 10 'fastjob health --database-url="postgresql://localhost/service_db"'

# Enterprise metrics monitoring  
watch -n 30 'fastjob metrics --database-url="postgresql://localhost/service_db"'
```

---

## Migration Guide

### From Global API to Instance API

```bash
# 1. Export existing jobs (if needed)
fastjob status > global_api_status.txt

# 2. Setup new service databases
fastjob setup --database-url="postgresql://localhost/user_service"
fastjob setup --database-url="postgresql://localhost/payment_service"

# 3. Update application code to use FastJob instances
# See examples/instance_api_example.py

# 4. Start new workers
fastjob worker --database-url="postgresql://localhost/user_service" --concurrency 2
fastjob worker --database-url="postgresql://localhost/payment_service" --concurrency 1

# 5. Verify new setup
fastjob status --database-url="postgresql://localhost/user_service"
fastjob status --database-url="postgresql://localhost/payment_service"
```

### From Single-Tenant to Multi-Tenant

```bash
# 1. Create tenant-specific databases
for tenant in tenant_a tenant_b tenant_c; do
  createdb "${tenant}_jobs"
  fastjob setup --database-url="postgresql://localhost/${tenant}_jobs"
done

# 2. Start tenant-specific workers
for tenant in tenant_a tenant_b tenant_c; do
  fastjob worker --database-url="postgresql://localhost/${tenant}_jobs" --concurrency 2 &
done

# 3. Update application code to use tenant-specific instances
# See examples/microservices_example.py (multi-tenant section)
```

---

This CLI reference covers all FastJob commands with both Global and Instance API usage patterns. For more examples and patterns, see the [examples directory](../examples/) and [production deployment guide](production.md).