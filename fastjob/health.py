"""
FastJob Health Check and Readiness Probe System
Provides health monitoring capabilities for FastJob workers and components.
"""

import asyncio
import logging
import time
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional, Tuple

from .db.connection import get_pool


class HealthStatus(Enum):
    """Health check status values."""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


class HealthCheck:
    """Individual health check component."""

    def __init__(
        self,
        name: str,
        check_func: callable,
        timeout: float = 5.0,
        critical: bool = True,
        interval: float = 30.0,
    ):
        self.name = name
        self.check_func = check_func
        self.timeout = timeout
        self.critical = critical
        self.interval = interval
        self.last_check = None
        self.last_status = HealthStatus.UNKNOWN
        self.last_message = "Not checked yet"
        self.last_duration = 0.0


class HealthMonitor:
    """Health monitoring system for FastJob."""

    def __init__(self):
        self.checks: Dict[str, HealthCheck] = {}
        self.logger = logging.getLogger(__name__)
        self._monitoring = False
        self._monitor_task = None

    def add_check(
        self,
        name: str,
        check_func: callable,
        timeout: float = 5.0,
        critical: bool = True,
        interval: float = 30.0,
    ):
        """Add a health check."""
        self.checks[name] = HealthCheck(
            name=name,
            check_func=check_func,
            timeout=timeout,
            critical=critical,
            interval=interval,
        )
        self.logger.info(f"Added health check: {name}")

    async def run_check(self, check: HealthCheck) -> Tuple[HealthStatus, str, float]:
        """Run a single health check."""
        start_time = time.time()

        try:
            # Run check with timeou
            result = await asyncio.wait_for(check.check_func(), timeout=check.timeout)

            duration = time.time() - start_time

            if isinstance(result, tuple):
                status, message = result
            elif isinstance(result, bool):
                status = HealthStatus.HEALTHY if result else HealthStatus.UNHEALTHY
                message = "Check passed" if result else "Check failed"
            else:
                status = HealthStatus.HEALTHY
                message = str(result)

            return status, message, duration

        except asyncio.TimeoutError:
            duration = time.time() - start_time
            return (
                HealthStatus.UNHEALTHY,
                f"Check timed out after {check.timeout}s",
                duration,
            )

        except Exception as e:
            duration = time.time() - start_time
            return HealthStatus.UNHEALTHY, f"Check failed: {str(e)}", duration

    async def check_health(self, check_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Run health checks and return status.

        Args:
            check_name: Run specific check only, or all checks if None

        Returns:
            Health status report
        """
        if check_name:
            if check_name not in self.checks:
                return {
                    "status": HealthStatus.UNKNOWN.value,
                    "message": f"Health check '{check_name}' not found",
                    "checks": {},
                }
            checks_to_run = {check_name: self.checks[check_name]}
        else:
            checks_to_run = self.checks

        check_results = {}
        overall_status = HealthStatus.HEALTHY
        critical_failures = []

        for name, check in checks_to_run.items():
            status, message, duration = await self.run_check(check)

            # Update check state
            check.last_check = datetime.now()
            check.last_status = status
            check.last_message = message
            check.last_duration = duration

            check_results[name] = {
                "status": status.value,
                "message": message,
                "duration_ms": round(duration * 1000, 2),
                "critical": check.critical,
                "last_check": check.last_check.isoformat(),
                "timeout": check.timeout,
            }

            # Determine overall status
            if status == HealthStatus.UNHEALTHY:
                if check.critical:
                    overall_status = HealthStatus.UNHEALTHY
                    critical_failures.append(name)
                elif overall_status == HealthStatus.HEALTHY:
                    overall_status = HealthStatus.DEGRADED
            elif (
                status == HealthStatus.DEGRADED
                and overall_status == HealthStatus.HEALTHY
            ):
                overall_status = HealthStatus.DEGRADED

        # Create summary message
        if overall_status == HealthStatus.HEALTHY:
            message = "All health checks passed"
        elif overall_status == HealthStatus.DEGRADED:
            message = "Some non-critical checks failed"
        else:
            message = f"Critical health checks failed: {', '.join(critical_failures)}"

        return {
            "status": overall_status.value,
            "message": message,
            "timestamp": datetime.now().isoformat(),
            "checks": check_results,
        }

    async def start_monitoring(self, interval: float = 30.0):
        """Start continuous health monitoring."""
        if self._monitoring:
            return

        self._monitoring = True
        self.logger.info("Starting health monitoring")

        async def monitor_loop():
            while self._monitoring:
                try:
                    await self.check_health()
                    await asyncio.sleep(interval)
                except Exception as e:
                    self.logger.error(f"Health monitoring error: {e}")
                    await asyncio.sleep(5)  # Short retry interval on error

        self._monitor_task = asyncio.create_task(monitor_loop())

    async def stop_monitoring(self):
        """Stop continuous health monitoring."""
        if not self._monitoring:
            return

        self._monitoring = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        self.logger.info("Stopped health monitoring")


# Global health monitor instance
_health_monitor = HealthMonitor()


async def check_database_health() -> Tuple[HealthStatus, str]:
    """Check database connectivity and basic operations."""
    try:
        pool = await get_pool()

        async with pool.acquire() as conn:
            # Test basic connectivity
            result = await conn.fetchval("SELECT 1")
            if result != 1:
                return (
                    HealthStatus.UNHEALTHY,
                    "Database query returned unexpected result",
                )

            # Test FastJob tables exist
            tables_exist = await conn.fetchval(
                """
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_name = 'fastjob_jobs'
            """
            )

            if tables_exist == 0:
                return (
                    HealthStatus.UNHEALTHY,
                    "FastJob tables not found - run migrations",
                )

            # Test job queue operations
            job_count = await conn.fetchval("SELECT COUNT(*) FROM fastjob_jobs")

            return HealthStatus.HEALTHY, f"Database healthy, {job_count} jobs in queue"

    except Exception as e:
        return HealthStatus.UNHEALTHY, f"Database check failed: {str(e)}"


async def check_job_processing_health() -> Tuple[HealthStatus, str]:
    """Check job processing health by looking at recent activity."""
    try:
        pool = await get_pool()

        async with pool.acquire() as conn:
            # Check for stuck jobs
            stuck_jobs = await conn.fetchval(
                """
                SELECT COUNT(*) FROM fastjob_jobs
                WHERE status = 'queued'
                AND created_at < NOW() - INTERVAL '1 hour'
                AND (scheduled_at IS NULL OR scheduled_at < NOW() - INTERVAL '1 hour')
            """
            )

            if stuck_jobs > 100:
                return HealthStatus.DEGRADED, f"{stuck_jobs} jobs may be stuck in queue"

            # Check for recent processing activity
            recent_activity = await conn.fetchval(
                """
                SELECT COUNT(*) FROM fastjob_jobs
                WHERE updated_at > NOW() - INTERVAL '5 minutes'
            """
            )

            # Check failed job rate
            failed_jobs = await conn.fetchval(
                """
                SELECT COUNT(*) FROM fastjob_jobs
                WHERE status = 'failed'
                AND updated_at > NOW() - INTERVAL '1 hour'
            """
            )

            total_recent_jobs = await conn.fetchval(
                """
                SELECT COUNT(*) FROM fastjob_jobs
                WHERE updated_at > NOW() - INTERVAL '1 hour'
            """
            )

            if total_recent_jobs > 0:
                failure_rate = (failed_jobs / total_recent_jobs) * 100
                if failure_rate > 50:
                    return (
                        HealthStatus.DEGRADED,
                        f"High failure rate: {failure_rate:.1f}%",
                    )

            return (
                HealthStatus.HEALTHY,
                f"Job processing healthy, {recent_activity} recent updates",
            )

    except Exception as e:
        return HealthStatus.UNHEALTHY, f"Job processing check failed: {str(e)}"


async def check_system_resources() -> Tuple[HealthStatus, str]:
    """Check system resource usage."""
    try:
        import psutil

        # Check memory usage
        memory = psutil.virtual_memory()
        if memory.percent > 90:
            return HealthStatus.DEGRADED, f"High memory usage: {memory.percent:.1f}%"

        # Check disk usage
        disk = psutil.disk_usage("/")
        if disk.percent > 90:
            return HealthStatus.DEGRADED, f"High disk usage: {disk.percent:.1f}%"

        # Check CPU usage (average over 1 second)
        cpu_percent = psutil.cpu_percent(interval=1)
        if cpu_percent > 95:
            return HealthStatus.DEGRADED, f"High CPU usage: {cpu_percent:.1f}%"

        return (
            HealthStatus.HEALTHY,
            f"Resources healthy (CPU: {cpu_percent:.1f}%, Mem: {memory.percent:.1f}%, Disk: {disk.percent:.1f}%)",
        )

    except ImportError:
        return HealthStatus.UNKNOWN, "psutil not available for resource monitoring"
    except Exception as e:
        return HealthStatus.UNHEALTHY, f"Resource check failed: {str(e)}"


def setup_default_health_checks():
    """Set up default health checks for FastJob."""
    _health_monitor.add_check(
        name="database",
        check_func=check_database_health,
        timeout=5.0,
        critical=True,
        interval=30.0,
    )

    _health_monitor.add_check(
        name="job_processing",
        check_func=check_job_processing_health,
        timeout=10.0,
        critical=False,
        interval=60.0,
    )

    _health_monitor.add_check(
        name="system_resources",
        check_func=check_system_resources,
        timeout=3.0,
        critical=False,
        interval=30.0,
    )


async def get_health_status(check_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Get current health status.

    Args:
        check_name: Specific check to run, or all checks if None

    Returns:
        Health status report
    """
    if not _health_monitor.checks:
        setup_default_health_checks()

    return await _health_monitor.check_health(check_name)


async def is_healthy() -> bool:
    """
    Quick health check returning boolean.

    Returns:
        True if all critical checks pass, False otherwise
    """
    status = await get_health_status()
    return status["status"] in [HealthStatus.HEALTHY.value, HealthStatus.DEGRADED.value]


async def is_ready() -> bool:
    """
    Readiness probe - checks if service is ready to handle requests.

    Returns:
        True if ready, False otherwise
    """
    try:
        # Check database connectivity
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")

        # Check that FastJob tables exist
        async with pool.acquire() as conn:
            tables_exist = await conn.fetchval(
                """
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_name = 'fastjob_jobs'
            """
            )

            return tables_exist > 0

    except Exception:
        return False


def add_health_check(
    name: str,
    check_func: callable,
    timeout: float = 5.0,
    critical: bool = True,
    interval: float = 30.0,
):
    """
    Add a custom health check.

    Args:
        name: Unique name for the check
        check_func: Async function that returns (status, message) or boolean
        timeout: Timeout for the check in seconds
        critical: Whether this check is critical for overall health
        interval: How often to run this check in seconds
    """
    _health_monitor.add_check(name, check_func, timeout, critical, interval)


async def start_health_monitoring(interval: float = 30.0):
    """Start continuous health monitoring."""
    if not _health_monitor.checks:
        setup_default_health_checks()

    await _health_monitor.start_monitoring(interval)


async def stop_health_monitoring():
    """Stop continuous health monitoring."""
    await _health_monitor.stop_monitoring()


# CLI health check function
async def cli_health_check(verbose: bool = False) -> int:
    """
    CLI health check function.

    Args:
        verbose: Show detailed check results

    Returns:
        Exit code (0 = healthy, 1 = unhealthy)
    """
    try:
        from .cli.colors import (
            StatusIcon,
            print_key_value,
            print_status,
            warning,
        )

        status = await get_health_status()

        if verbose:
            # Print header
            from .cli.colors import print_header

            print_header("FastJob Health Check")

            # Overall status
            if status["status"] == "healthy":
                print_status(f"Overall Status: {status['status'].upper()}", "success")
            elif status["status"] == "degraded":
                print_status(f"Overall Status: {status['status'].upper()}", "warning")
            else:
                print_status(f"Overall Status: {status['status'].upper()}", "error")

            print_key_value("Message", status["message"])
            print_key_value("Timestamp", status["timestamp"])

            print("\nIndividual Checks:")
            for check_name, check_result in status["checks"].items():
                if check_result["status"] == "healthy":
                    icon = StatusIcon.success()
                elif check_result["status"] == "unhealthy":
                    icon = StatusIcon.error()
                else:
                    icon = StatusIcon.warning()

                critical_marker = (
                    warning(" (CRITICAL)") if check_result["critical"] else ""
                )
                duration_info = f"({check_result['duration_ms']}ms)"

                print(
                    f"  {icon} {check_name}{critical_marker}: {check_result['message']} {duration_info}"
                )
        else:
            # Simple output
            if status["status"] == "healthy":
                print_status(
                    f"{status['status'].upper()}: {status['message']}", "success"
                )
            elif status["status"] == "degraded":
                print_status(
                    f"{status['status'].upper()}: {status['message']}", "warning"
                )
            else:
                print_status(
                    f"{status['status'].upper()}: {status['message']}", "error"
                )

        return 0 if status["status"] in ["healthy", "degraded"] else 1

    except Exception as e:
        from .cli.colors import print_status

        print_status(f"Health check failed - {str(e)}", "error")
        return 1


# CLI readiness check function
async def cli_readiness_check() -> int:
    """
    CLI readiness check function.

    Returns:
        Exit code (0 = ready, 1 = not ready)
    """
    try:
        from .cli.colors import print_status

        ready = await is_ready()
        if ready:
            print_status("Service is ready to handle requests", "success")
            return 0
        else:
            print_status("Service is not ready", "error")
            return 1

    except Exception as e:
        from .cli.colors import print_status

        print_status(f"Readiness check failed - {str(e)}", "error")
        return 1
