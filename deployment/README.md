# FastJob Production Deployment Guide

This directory contains production deployment configurations for FastJob across different platforms and process managers.

## Quick Start

Choose your deployment method:

- **[Supervisor](#supervisor-deployment)** - Simple process management
- **[systemd](#systemd-deployment)** - Modern Linux service management  
- **[Docker Compose](#docker-compose-deployment)** - Containerized deployment
- **[Kubernetes](#kubernetes-deployment)** - Scalable orchestration

## Prerequisites

### System Requirements

- **Python 3.10+**
- **PostgreSQL 12+** (recommended 15+)
- **2GB RAM minimum** (4GB+ recommended for production)
- **2 CPU cores minimum** (4+ recommended for production)

### Database Setup

```bash
# Create PostgreSQL database
createdb fastjob_prod

# Create dedicated user
psql -c "CREATE USER fastjob WITH PASSWORD 'your_secure_password';"
psql -c "GRANT ALL PRIVILEGES ON DATABASE fastjob_prod TO fastjob;"

# Run migrations
export FASTJOB_DATABASE_URL="postgresql://fastjob:your_secure_password@localhost/fastjob_prod"
# For remote databases, replace localhost with your database server IP/hostname
# export FASTJOB_DATABASE_URL="postgresql://fastjob:your_secure_password@db.example.com/fastjob_prod"
fastjob migrate
```

### Application User

```bash
# Create dedicated system user
sudo useradd --system --create-home --shell /bin/bash fastjob

# Create directories
sudo mkdir -p /opt/fastjob /var/log/fastjob
sudo chown fastjob:fastjob /opt/fastjob /var/log/fastjob

# Install FastJob
sudo -u fastjob python -m venv /opt/fastjob/venv
sudo -u fastjob /opt/fastjob/venv/bin/pip install fastjob
# For Pro: sudo -u fastjob /opt/fastjob/venv/bin/pip install fastjob-pro[dashboard]
# For Enterprise: sudo -u fastjob /opt/fastjob/venv/bin/pip install fastjob-enterprise[all]
```

## Supervisor Deployment

Supervisor provides simple process management with automatic restarts.

### Installation

```bash
# Install Supervisor
sudo apt-get install supervisor

# Copy configuration
sudo cp supervisor.conf /etc/supervisor/conf.d/fastjob.conf

# Update configuration with your settings
sudo nano /etc/supervisor/conf.d/fastjob.conf
# IMPORTANT: Update FASTJOB_DATABASE_URL to point to your database server
# If PostgreSQL is on a remote server, update the connection string accordingly

# Reload Supervisor
sudo supervisorctl reread
sudo supervisorctl update
```

### Management Commands

```bash
# Start all FastJob services
sudo supervisorctl start fastjob:*

# Check status
sudo supervisorctl status fastjob:*

# View logs
sudo supervisorctl tail -f fastjob_worker

# Restart services
sudo supervisorctl restart fastjob:*

# Stop services
sudo supervisorctl stop fastjob:*
```

## systemd Deployment

Modern Linux distributions prefer systemd for service management.

### Installation

```bash
# Copy service files
sudo cp fastjob-worker.service /etc/systemd/system/
sudo cp fastjob-dashboard.service /etc/systemd/system/  # Pro/Enterprise only

# Update configuration with your settings
sudo nano /etc/systemd/system/fastjob-worker.service
# IMPORTANT: 
# 1. Update FASTJOB_DATABASE_URL to point to your database server
# 2. If PostgreSQL runs on a remote server, uncomment and adjust the dependency lines
# 3. Remove postgresql.service dependency if PostgreSQL is not on the same server

sudo nano /etc/systemd/system/fastjob-dashboard.service  # Pro/Enterprise only
# Apply the same database URL and dependency changes

# Reload systemd
sudo systemctl daemon-reload

# Enable services
sudo systemctl enable fastjob-worker.service
sudo systemctl enable fastjob-dashboard.service  # Pro/Enterprise only
```

### Management Commands

```bash
# Start services
sudo systemctl start fastjob-worker
sudo systemctl start fastjob-dashboard  # Pro/Enterprise only

# Check status
sudo systemctl status fastjob-worker

# View logs
sudo journalctl -u fastjob-worker -f

# Restart services
sudo systemctl restart fastjob-worker

# Stop services
sudo systemctl stop fastjob-worker
```

## Docker Compose Deployment

Containerized deployment with Docker Compose provides isolation and easy scaling.

### Prerequisites

```bash
# Install Docker and Docker Compose
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
sudo apt-get install docker-compose-plugin
```

### Deployment

```bash
# Clone configuration
git clone <your-repo>
cd fastjob-deployment

# Create environment file
cp .env.example .env
nano .env  # Update with your configuration

# Build and start services
docker compose up -d

# Start with optional services
docker compose --profile priority --profile cache up -d
```

### Management Commands

```bash
# View status
docker compose ps

# View logs
docker compose logs -f fastjob_worker

# Scale workers
docker compose up -d --scale fastjob_worker=3

# Stop services
docker compose down

# Update images
docker compose pull && docker compose up -d
```

### Configuration Files

Create these additional files:

**`.env`**:
```bash
POSTGRES_PASSWORD=your_secure_password
FASTJOB_LOG_LEVEL=INFO
```

**`requirements.txt`**:
```
fastjob>=0.1.0
# fastjob-pro>=0.1.0  # For Pro edition
# fastjob-enterprise>=0.1.0  # For Enterprise edition
# Add your application dependencies here
```

## Kubernetes Deployment

For large-scale production deployments with high availability.

### Prerequisites

```bash
# Install kubectl
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl

# Verify cluster access
kubectl cluster-info
```

### Deployment

```bash
# Update secrets in kubernetes.yaml
echo -n "postgresql://fastjob:password@postgres:5432/fastjob_prod" | base64

# Apply configuration
kubectl apply -f kubernetes.yaml

# Check deployment status
kubectl get pods -n fastjob
kubectl get services -n fastjob
```

### Management Commands

```bash
# Scale workers
kubectl scale deployment fastjob-worker --replicas=5 -n fastjob

# View logs
kubectl logs -f deployment/fastjob-worker -n fastjob

# Port forward dashboard (for testing)
kubectl port-forward service/fastjob-dashboard-service 8000:80 -n fastjob

# Update deployment
kubectl rollout restart deployment/fastjob-worker -n fastjob
```

## Monitoring and Health Checks

### Health Check Endpoints

FastJob provides built-in health checking:

```bash
# Basic health check
fastjob health

# Detailed health information  
fastjob health --verbose

# Readiness probe
fastjob ready
```

### HTTP Health Endpoints (Pro/Enterprise Dashboard)

- `GET /health` - Overall health status
- `GET /ready` - Readiness probe
- `GET /metrics` - Prometheus metrics (Enterprise)

### Monitoring Integration

**Prometheus Configuration**:
```yaml
scrape_configs:
  - job_name: 'fastjob'
    static_configs:
      - targets: ['fastjob-dashboard:8000']
    metrics_path: '/metrics'
    scrape_interval: 30s
```

**Grafana Dashboard**: Import the provided dashboard configuration for FastJob metrics visualization.

## Security Considerations

### Database Security

- Use strong passwords for database connections
- Enable SSL/TLS for database connections in production
- Restrict database access to FastJob services only
- Regular security updates for PostgreSQL

### Application Security

- Run FastJob services as dedicated non-root user
- Use environment variables for sensitive configuration
- Enable firewall rules to restrict network access
- Regular security updates for Python and dependencies

### Network Security

- Use reverse proxy (nginx) for dashboard access
- Enable HTTPS with proper SSL certificates
- Implement rate limiting for API endpoints
- Use VPN or private networks for internal communication

## Performance Tuning

### Worker Configuration

```bash
# Adjust concurrency based on workload
fastjob worker --concurrency=8  # CPU-bound tasks
fastjob worker --concurrency=16 # I/O-bound tasks

# Use multiple queues for prioritization
fastjob worker --queues=urgent,default,background
```

### Database Performance

```sql
-- Add indexes for better performance
CREATE INDEX CONCURRENTLY idx_fastjob_jobs_status_queue ON fastjob_jobs(status, queue);
CREATE INDEX CONCURRENTLY idx_fastjob_jobs_scheduled_at ON fastjob_jobs(scheduled_at) WHERE scheduled_at IS NOT NULL;

-- Optimize PostgreSQL settings
# In postgresql.conf:
shared_buffers = 256MB
effective_cache_size = 1GB
maintenance_work_mem = 64MB
checkpoint_completion_target = 0.9
wal_buffers = 16MB
default_statistics_target = 100
```

### System Resources

- **Memory**: 512MB per worker process minimum
- **CPU**: 1 core per 4 concurrent jobs recommended  
- **Disk**: Fast SSD storage for database
- **Network**: Low latency connection to database

## Backup and Recovery

### Database Backups

```bash
# Daily backup script
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
pg_dump $FASTJOB_DATABASE_URL > /backup/fastjob_backup_$DATE.sql
find /backup -name "fastjob_backup_*.sql" -mtime +7 -delete
```

### Application State

FastJob is stateless, but consider backing up:
- Job definitions and application code
- Configuration files
- Log files for audit purposes

## Troubleshooting

### Common Issues

**Workers not processing jobs**:
```bash
# Check database connectivity
fastjob health --verbose

# Check for stuck jobs
psql $FASTJOB_DATABASE_URL -c "SELECT COUNT(*) FROM fastjob_jobs WHERE status='queued' AND created_at < NOW() - INTERVAL '1 hour';"

# Restart workers
sudo systemctl restart fastjob-worker
```

**High memory usage**:
```bash
# Reduce worker concurrency
# Monitor job memory usage
# Check for memory leaks in job functions
```

**Database connection errors**:
```bash
# Check PostgreSQL is running
sudo systemctl status postgresql

# Verify connection string
fastjob ready

# Check connection limits
psql $FASTJOB_DATABASE_URL -c "SELECT * FROM pg_stat_activity;"
```

### Log Locations

- **Supervisor**: `/var/log/fastjob/`
- **systemd**: `journalctl -u fastjob-worker`
- **Docker**: `docker compose logs`
- **Kubernetes**: `kubectl logs -n fastjob`

### Getting Help

- Check the [FastJob documentation](https://docs.fastjob.dev)
- Review application logs for error details
- Use health checks to identify component issues
- Monitor system resources and database performance

For additional support, contact [support@fastjob.dev](mailto:support@fastjob.dev) with your deployment configuration and error logs.