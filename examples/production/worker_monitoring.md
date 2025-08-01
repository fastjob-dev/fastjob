# FastJob Worker Monitoring Examples

Comprehensive examples for monitoring FastJob workers in production environments.

## Basic Worker Monitoring

### Check Worker Status
```bash
# Quick system overview
fastjob status
# Output: "Workers: 3 active, 1 stale (use 'fastjob workers' for details)"

# Detailed worker information
fastjob workers
```

Example output:
```
👥 FastJob Worker Status

Health: HEALTHY
Active Workers: 2
Stopped Workers: 0
Total Concurrency: 8

Active Workers:
  🟢 hostname-1:1234
     Queues: all queues
     Concurrency: 4
     Uptime: 2h 15m 30s
     Last Heartbeat: 2025-01-26T14:30:45
     CPU: 2.5%
     Memory: 45.2 MB

  🟢 hostname-2:5678
     Queues: critical, emails
     Concurrency: 4
     Uptime: 1h 45m 12s
     Last Heartbeat: 2025-01-26T14:30:43
```

### Worker Lifecycle

1. **Startup**: Worker registers with unique ID (hostname:PID)
2. **Running**: Sends heartbeat every 5 seconds with system metrics
3. **Graceful Shutdown**: Worker marks itself as 'stopped' 
4. **Crash Detection**: Missing heartbeats trigger 'stale' status
5. **Cleanup**: `fastjob workers --cleanup` removes stale records

## Production Integration

### Kubernetes Health Checks

**Readiness probe:**
```yaml
readinessProbe:
  exec:
    command: ["fastjob", "status"]
  initialDelaySeconds: 10
  periodSeconds: 30
  failureThreshold: 3
```

**Liveness probe:**
```yaml
livenessProbe:
  exec:
    command: ["fastjob", "status"]
  initialDelaySeconds: 60
  periodSeconds: 60
  failureThreshold: 5
```

### Monitoring Script Examples

**Simple health check:**
```bash
#!/bin/bash
# health_check.sh
fastjob status > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "FastJob healthy"
    exit 0
else
    echo "FastJob unhealthy"
    exit 1
fi
```

**Worker monitoring with alerting:**
```bash
#!/bin/bash
# monitor_workers.sh

# Check for stale workers
fastjob workers --stale > /tmp/stale_workers.txt
if [ -s /tmp/stale_workers.txt ]; then
    echo "ALERT: Stale workers detected"
    cat /tmp/stale_workers.txt
    
    # Send to alerting system (Slack, PagerDuty, etc.)
    curl -X POST -H 'Content-type: application/json' \
        --data '{"text":"FastJob stale workers detected"}' \
        $SLACK_WEBHOOK_URL
    
    exit 1
fi

echo "All workers healthy"
exit 0
```

**Automated recovery workflow:**
```bash
#!/bin/bash
# auto_recovery.sh

echo "Checking FastJob worker health..."

# 1. Check system health
if ! fastjob status > /dev/null 2>&1; then
    echo "ERROR: FastJob system unhealthy"
    exit 1
fi

# 2. Check for stale workers
fastjob workers --stale > /tmp/stale_check.txt
if [ -s /tmp/stale_check.txt ]; then
    echo "Found stale workers, initiating recovery..."
    cat /tmp/stale_check.txt
    
    # Restart worker service
    systemctl restart fastjob-worker
    sleep 15
    
    # Clean up stale records
    fastjob workers --cleanup
    
    echo "Recovery completed"
else
    echo "All workers healthy"
fi

# 3. Check if we need more workers
active_workers=$(fastjob workers | grep "🟢" | wc -l)
min_workers=3

if [ $active_workers -lt $min_workers ]; then
    echo "Scaling up workers (current: $active_workers, minimum: $min_workers)"
    
    # Scale up based on your orchestration system
    if command -v kubectl &> /dev/null; then
        kubectl scale deployment fastjob-worker --replicas=5
    elif command -v systemctl &> /dev/null; then
        systemctl start fastjob-worker@{2..5}
    fi
fi
```

### Prometheus Metrics Integration

**Script to export worker metrics:**
```bash
#!/bin/bash
# export_metrics.sh

# Create metrics file for Prometheus node_exporter
METRICS_FILE="/var/lib/node_exporter/textfile_collector/fastjob.prom"

# Get worker status
fastjob workers > /tmp/worker_status.txt 2>/dev/null

# Extract metrics
total_workers=$(grep "Active Workers:" /tmp/worker_status.txt | awk '{print $3}')
total_concurrency=$(grep "Total Concurrency:" /tmp/worker_status.txt | awk '{print $3}')

# Write Prometheus metrics
cat > $METRICS_FILE << EOF
# HELP fastjob_active_workers Number of active FastJob workers
# TYPE fastjob_active_workers gauge
fastjob_active_workers ${total_workers:-0}

# HELP fastjob_total_concurrency Total concurrency across all workers
# TYPE fastjob_total_concurrency gauge
fastjob_total_concurrency ${total_concurrency:-0}

# HELP fastjob_system_healthy FastJob system health status
# TYPE fastjob_system_healthy gauge
EOF

# Check system health
if fastjob status > /dev/null 2>&1; then
    echo "fastjob_system_healthy 1" >> $METRICS_FILE
else
    echo "fastjob_system_healthy 0" >> $METRICS_FILE
fi

echo "Metrics exported to $METRICS_FILE"
```

**Cron job for metrics collection:**
```bash
# Add to crontab: crontab -e
# Collect metrics every minute
* * * * * /path/to/export_metrics.sh
```

### Docker Swarm Health Checks

**docker-compose.yml with health checks:**
```yaml
version: '3.8'
services:
  fastjob-worker:
    image: myapp:latest
    command: fastjob start --concurrency 4
    healthcheck:
      test: ["CMD", "fastjob", "status"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    deploy:
      replicas: 3
      restart_policy:
        condition: on-failure
        delay: 10s
        max_attempts: 3
```

### Systemd Integration

**Service file with monitoring:**
```ini
# /etc/systemd/system/fastjob-worker.service
[Unit]
Description=FastJob Worker
After=postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=myapp
WorkingDirectory=/path/to/myapp
Environment=FASTJOB_DATABASE_URL=postgresql://...
ExecStart=/path/to/venv/bin/fastjob start --concurrency 4
ExecReload=/bin/kill -HUP $MAINPID
Restart=always
RestartSec=10
StartLimitInterval=0

# Health monitoring
ExecStartPost=/bin/sleep 10
ExecStartPost=/path/to/health_check.sh

[Install]
WantedBy=multi-user.target
```

**Monitoring timer:**
```ini
# /etc/systemd/system/fastjob-monitor.service
[Unit]
Description=FastJob Worker Monitor
Requires=fastjob-worker.service

[Service]
Type=oneshot
ExecStart=/path/to/monitor_workers.sh

# /etc/systemd/system/fastjob-monitor.timer
[Unit]
Description=Run FastJob Monitor every 5 minutes
Requires=fastjob-monitor.service

[Timer]
OnCalendar=*:0/5
Persistent=true

[Install]
WantedBy=timers.target
```

## Configuration

### Environment Variables
```bash
# Heartbeat interval (default: 5.0 seconds)
export FASTJOB_WORKER_HEARTBEAT_INTERVAL=5.0

# Database connection
export FASTJOB_DATABASE_URL="postgresql://user:password@localhost/myapp"
```

### Monitoring Best Practices

1. **Regular Health Checks**: Run `fastjob status` every 30-60 seconds
2. **Stale Worker Detection**: Check for stale workers every 5 minutes
3. **Automatic Cleanup**: Run `fastjob workers --cleanup` after service restarts
4. **Capacity Monitoring**: Alert when active worker count drops below threshold
5. **Log Monitoring**: Monitor worker logs for errors and exceptions

### Troubleshooting

**No workers showing up:**
```bash
# Check if worker is running
ps aux | grep fastjob

# Check worker logs
journalctl -u fastjob-worker -f

# Check database connectivity
fastjob status
```

**Stale workers not cleaning up:**
```bash
# Manually clean up stale workers
fastjob workers --stale
fastjob workers --cleanup

# Restart worker service
systemctl restart fastjob-worker
```

**High worker turnover:**
```bash
# Check for resource constraints
free -h
df -h

# Check for OOM kills
dmesg | grep -i "killed process"

# Check worker resource usage
fastjob workers  # Shows CPU and memory per worker
```