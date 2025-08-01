#!/bin/bash
# FastJob Production Monitoring and Auto-Recovery Script
# 
# This script monitors FastJob workers and automatically handles common issues:
# - Detects stale/dead workers
# - Restarts services when needed
# - Scales workers based on demand
# - Sends alerts for critical issues
#
# Usage: ./monitor_and_restart.sh
# Recommended: Run from cron every 5 minutes

set -euo pipefail

# Configuration
MIN_WORKERS=2
SLACK_WEBHOOK_URL="${SLACK_WEBHOOK_URL:-}"
LOG_FILE="/var/log/fastjob-monitor.log"

# Logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# Alert function
alert() {
    local message="$1"
    log "ALERT: $message"
    
    if [ -n "$SLACK_WEBHOOK_URL" ]; then
        curl -s -X POST -H 'Content-type: application/json' \
            --data "{\"text\":\"🚨 FastJob Alert: $message\"}" \
            "$SLACK_WEBHOOK_URL" || log "Failed to send Slack alert"
    fi
}

# Check if FastJob system is healthy
check_system_health() {
    log "Checking FastJob system health..."
    
    if ! fastjob status >/dev/null 2>&1; then
        alert "FastJob system is unhealthy - database connection failed"
        return 1
    fi
    
    log "System health check passed"
    return 0
}

# Check for stale workers and clean them up
handle_stale_workers() {
    log "Checking for stale workers..."
    
    local stale_file="/tmp/fastjob_stale_workers.txt"
    fastjob workers --stale > "$stale_file" 2>/dev/null
    
    if [ -s "$stale_file" ]; then
        log "Found stale workers:"
        cat "$stale_file" | tee -a "$LOG_FILE"
        
        alert "Stale workers detected - initiating restart"
        
        # Restart the service
        log "Restarting FastJob worker service..."
        if systemctl restart fastjob-worker; then
            log "Service restarted successfully"
            sleep 15  # Give workers time to start
            
            # Clean up stale records
            fastjob workers --cleanup
            log "Cleaned up stale worker records"
        else
            alert "Failed to restart FastJob worker service"
            return 1
        fi
    else
        log "No stale workers found"
    fi
    
    rm -f "$stale_file"
    return 0
}

# Check if we have enough active workers
check_worker_capacity() {
    log "Checking worker capacity..."
    
    # Count active workers (lines with 🟢 emoji)
    local active_workers
    active_workers=$(fastjob workers 2>/dev/null | grep -c "🟢" || echo "0")
    
    log "Active workers: $active_workers (minimum required: $MIN_WORKERS)"
    
    if [ "$active_workers" -lt "$MIN_WORKERS" ]; then
        alert "Insufficient workers: $active_workers/$MIN_WORKERS - scaling up"
        
        # Scale based on your orchestration system
        if command -v kubectl >/dev/null 2>&1; then
            # Kubernetes
            local desired_replicas=$((MIN_WORKERS + 1))
            kubectl scale deployment fastjob-worker --replicas="$desired_replicas"
            log "Scaled Kubernetes deployment to $desired_replicas replicas"
        elif command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
            # Docker Swarm
            local desired_replicas=$((MIN_WORKERS + 1))
            docker service scale myapp_fastjob-worker="$desired_replicas"
            log "Scaled Docker service to $desired_replicas replicas"
        else
            # Systemd
            systemctl start fastjob-worker
            log "Started additional systemd worker"
        fi
    else
        log "Worker capacity is sufficient"
    fi
}

# Display current status
show_status() {
    log "=== Current FastJob Status ==="
    fastjob status 2>/dev/null | tee -a "$LOG_FILE" || log "Failed to get status"
    
    log "=== Worker Details ==="
    fastjob workers 2>/dev/null | tee -a "$LOG_FILE" || log "Failed to get worker details"
}

# Main execution
main() {
    log "Starting FastJob monitoring check..."
    
    # Create log file if it doesn't exist
    touch "$LOG_FILE"
    
    # Check system health first
    if ! check_system_health; then
        alert "System health check failed - aborting monitoring"
        exit 1
    fi
    
    # Handle stale workers
    handle_stale_workers
    
    # Check worker capacity
    check_worker_capacity
    
    # Show final status
    show_status
    
    log "Monitoring check completed successfully"
}

# Error handling
trap 'log "Script failed with error on line $LINENO"' ERR

# Run main function
main "$@"