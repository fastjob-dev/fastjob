# 🚀 FastJob Production Deployment Guide

**Deploy FastJob to production with confidence** - This guide covers everything from simple process management to Kubernetes orchestration.

---

## 📋 Quick Start

Choose your deployment method:

| Method | Best For | Complexity | 
|--------|----------|------------|
| [**Supervisor**](#supervisor-deployment) | Simple production setups | ⭐ Easy |
| [**systemd**](#systemd-deployment) | Modern Linux servers | ⭐⭐ Medium |
| [**Docker Compose**](#docker-compose-deployment) | Containerized apps | ⭐⭐ Medium |
| [**Kubernetes**](#kubernetes-deployment) | Large scale deployments | ⭐⭐⭐ Advanced |

---

## 🔧 Prerequisites

### ✅ System Requirements

**Minimum Requirements:**
- Python 3.10+
- PostgreSQL 12+
- 2GB RAM, 2 CPU cores

**Recommended for Production:**
- Python 3.12+
- PostgreSQL 15+
- 4GB+ RAM, 4+ CPU cores
- Fast SSD storage for database

### 🗄️ Database Setup

FastJob works with **any PostgreSQL setup** - local, remote, or cloud:

```bash
# 1. Create database
createdb fastjob_prod

# 2. Create dedicated user (recommended)
psql -c "CREATE USER fastjob WITH PASSWORD 'your_secure_password';"
psql -c "GRANT ALL PRIVILEGES ON DATABASE fastjob_prod TO fastjob;"

# 3. Set connection URL
export FASTJOB_DATABASE_URL="postgresql://fastjob:your_secure_password@localhost/fastjob_prod"

# For remote databases (AWS RDS, Google Cloud SQL, etc.)
# export FASTJOB_DATABASE_URL="postgresql://user:pass@your-db-host:5432/fastjob_prod"

# 4. Initialize schema
fastjob migrate
```

✅ **Database is ready!** FastJob will connect automatically.

### 👤 Application User (Linux)

```bash
# Create dedicated system user
sudo useradd --system --create-home --shell /bin/bash fastjob

# Create application directories
sudo mkdir -p /opt/fastjob /var/log/fastjob
sudo chown fastjob:fastjob /opt/fastjob /var/log/fastjob
```

---

## 🎯 Deployment Methods

### 1. Supervisor Deployment ⭐

**Perfect for:** Simple production setups, shared hosting, traditional servers

#### Install Supervisor
```bash
# Ubuntu/Debian
sudo apt install supervisor

# CentOS/RHEL
sudo yum install supervisor
```

#### Setup FastJob
```bash
# Install in virtual environment
sudo -u fastjob python3 -m venv /opt/fastjob/venv
sudo -u fastjob /opt/fastjob/venv/bin/pip install fastjob

# Copy configuration
sudo cp supervisor.conf /etc/supervisor/conf.d/fastjob.conf

# Update database URL in the config file
sudo nano /etc/supervisor/conf.d/fastjob.conf
```

#### Start Services
```bash
# Reload supervisor configuration  
sudo supervisorctl reread
sudo supervisorctl update

# Start FastJob services
sudo supervisorctl start fastjob_worker
sudo supervisorctl start fastjob_dashboard  # Pro/Enterprise only

# Check status
sudo supervisorctl status
```

**✅ Done!** Workers are running and will auto-restart if they crash.

---

### 2. systemd Deployment ⭐⭐

**Perfect for:** Modern Linux servers, automated deployments, production environments

#### Setup FastJob
```bash
# Install FastJob
sudo -u fastjob python3 -m venv /opt/fastjob/venv
sudo -u fastjob /opt/fastjob/venv/bin/pip install fastjob

# Copy service files
sudo cp fastjob-worker.service /etc/systemd/system/
sudo cp fastjob-dashboard.service /etc/systemd/system/  # Pro/Enterprise only

# Update database URLs in service files
sudo nano /etc/systemd/system/fastjob-worker.service
```

#### Configure Services
```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable services (auto-start on boot)
sudo systemctl enable fastjob-worker
sudo systemctl enable fastjob-dashboard  # Pro/Enterprise only

# Start services
sudo systemctl start fastjob-worker
sudo systemctl start fastjob-dashboard  # Pro/Enterprise only
```

#### Monitor Services
```bash
# Check status
sudo systemctl status fastjob-worker

# View logs
sudo journalctl -u fastjob-worker -f

# Restart if needed
sudo systemctl restart fastjob-worker
```

**✅ Done!** Services are running and managed by systemd.

---

### 3. Docker Compose Deployment ⭐⭐

**Perfect for:** Containerized environments, development-to-production consistency

#### Prerequisites
- Docker 20.04+
- Docker Compose 2.0+

#### Deploy Stack
```bash
# Copy docker-compose.yml
cp docker-compose.yml /opt/fastjob/

# Set environment variables
export POSTGRES_PASSWORD=your_secure_password

# Start the complete stack
cd /opt/fastjob
docker-compose up -d
```

#### Stack Components
- **postgres** - PostgreSQL database
- **fastjob-worker** - Job processing workers  
- **fastjob-dashboard** - Web dashboard (Pro/Enterprise)

#### Monitor Stack
```bash
# View running containers
docker-compose ps

# View logs
docker-compose logs -f fastjob-worker

# Scale workers
docker-compose up -d --scale fastjob-worker=3
```

**✅ Done!** Complete FastJob stack running in containers.

---

### 4. Kubernetes Deployment ⭐⭐⭐

**Perfect for:** Large scale deployments, high availability, cloud environments

#### Prerequisites
- Kubernetes cluster 1.20+
- kubectl configured
- External PostgreSQL database

#### Deploy to Kubernetes
```bash
# Update database connection in kubernetes.yaml
# (Base64 encode your database URL)
echo -n "postgresql://user:pass@host/db" | base64

# Apply configuration  
kubectl apply -f kubernetes.yaml

# Verify deployment
kubectl get pods -l app=fastjob
kubectl get services -l app=fastjob
```

#### Scale Workers
```bash
# Scale workers based on load
kubectl scale deployment fastjob-worker --replicas=5

# Auto-scaling (requires metrics-server)
kubectl autoscale deployment fastjob-worker --cpu-percent=70 --min=2 --max=10
```

#### Monitor Deployment
```bash
# View pod status
kubectl get pods

# View logs
kubectl logs -l app=fastjob -f

# View metrics
kubectl top pods
```

**✅ Done!** FastJob running in Kubernetes with scaling and monitoring.

---

## 📊 Monitoring & Maintenance

### Health Checks
```bash
# Basic health check
fastjob health --verbose

# Readiness probe (for load balancers)  
fastjob ready
```

### Job Management
```bash
# View job status
fastjob jobs list --status failed --limit 20

# Monitor queues
fastjob status

# Manual job operations
fastjob jobs retry <job-id>
fastjob jobs cancel <job-id>
```

### Database Monitoring
```bash
# Check for stuck jobs
psql $FASTJOB_DATABASE_URL -c "
  SELECT COUNT(*) FROM fastjob_jobs 
  WHERE status='queued' AND created_at < NOW() - INTERVAL '1 hour';
"

# Connection monitoring
psql $FASTJOB_DATABASE_URL -c "SELECT * FROM pg_stat_activity;"
```

### Backup Strategy
```bash
#!/bin/bash
# Daily backup script
DATE=$(date +%Y%m%d_%H%M%S)
pg_dump $FASTJOB_DATABASE_URL > /backup/fastjob_backup_$DATE.sql
find /backup -name "fastjob_backup_*.sql" -mtime +7 -delete
```

---

## 🔧 Performance Tuning

### Worker Optimization
- **Memory**: 512MB per worker process minimum
- **CPU**: 1 core per 4 concurrent jobs recommended
- **Queues**: Separate queues by priority and type
  ```bash
  # Process all queues (default behavior)
  fastjob worker --concurrency 4
  
  # Or target specific queues only
  fastjob worker --queues urgent,background --concurrency 4
  ```

### Database Optimization
```sql
-- Add performance indexes
CREATE INDEX CONCURRENTLY idx_fastjob_jobs_status_queue ON fastjob_jobs(status, queue);
CREATE INDEX CONCURRENTLY idx_fastjob_jobs_scheduled_at ON fastjob_jobs(scheduled_at) WHERE scheduled_at IS NOT NULL;

-- Optimize PostgreSQL settings (in postgresql.conf)
shared_buffers = 256MB
work_mem = 4MB
max_connections = 200
```

### Connection Pooling
FastJob includes built-in connection pooling. For high-scale deployments:

```python
# In your FastJob configuration
FASTJOB_DB_POOL_MIN_SIZE = 10
FASTJOB_DB_POOL_MAX_SIZE = 50
```

---

## 🚨 Troubleshooting

### Common Issues

**Workers not processing jobs**
```bash
# Check database connectivity
fastjob health --verbose

# Check for stuck jobs
psql $FASTJOB_DATABASE_URL -c "SELECT COUNT(*) FROM fastjob_jobs WHERE status='queued';"

# Restart workers
sudo systemctl restart fastjob-worker
```

**High memory usage**
```bash
# Reduce worker concurrency
fastjob worker --concurrency 2

# Check for memory leaks in job functions
# Monitor with: htop or ps aux
```

**Database connection errors**
```bash
# Verify connection string
echo $FASTJOB_DATABASE_URL

# Test connection manually
psql $FASTJOB_DATABASE_URL -c "SELECT 1;"

# Check connection limits
psql $FASTJOB_DATABASE_URL -c "SELECT * FROM pg_stat_activity;"
```

### Log Analysis
```bash
# systemd logs
sudo journalctl -u fastjob-worker --since "1 hour ago"

# Supervisor logs  
sudo tail -f /var/log/supervisor/fastjob_worker.log

# Docker logs
docker-compose logs --since 1h fastjob-worker
```

---

## 📞 Support

- **Documentation**: [FastJob Docs](https://docs.fastjob.dev)
- **Issues**: [GitHub Issues](https://github.com/abhinavs/fastjob/issues)
- **Email**: abhinav@apiclabs.com

Built by [Abhinav Saxena](https://github.com/abhinavs) with ❤️