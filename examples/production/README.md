# FastJob Production Examples

Production-ready examples for monitoring, alerting, and automation with FastJob worker heartbeats.

## Files

### `worker_monitoring.md`
Comprehensive guide covering:
- Basic worker monitoring commands
- Production integration examples (Kubernetes, Docker, Systemd)
- Monitoring scripts for alerting systems
- Prometheus metrics integration
- Troubleshooting common issues

### `monitor_and_restart.sh`
Ready-to-use production monitoring script that:
- Checks system health
- Detects and cleans up stale workers
- Automatically restarts services when needed
- Scales workers based on demand
- Sends alerts via Slack/webhooks

## Quick Start

1. **Basic monitoring:**
   ```bash
   # Check system status
   fastjob status
   
   # View worker details
   fastjob workers
   ```

2. **Set up automated monitoring:**
   ```bash
   # Copy and configure the monitoring script
   cp monitor_and_restart.sh /usr/local/bin/
   chmod +x /usr/local/bin/monitor_and_restart.sh
   
   # Add to crontab (check every 5 minutes)
   echo "*/5 * * * * /usr/local/bin/monitor_and_restart.sh" | crontab -
   ```

3. **Configure alerts:**
   ```bash
   export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK"
   ```

## Key Concepts

- **Workers** register with hostname:PID (e.g., `server-1:1234`)
- **Heartbeats** sent every 5 seconds
- **Stale detection** after 5 minutes of no heartbeat
- **Automatic cleanup** removes dead worker records

For detailed examples and configuration options, see `worker_monitoring.md`.