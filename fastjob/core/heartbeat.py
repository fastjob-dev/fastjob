"""
Worker Heartbeat System

Provides worker registration, heartbeat updates, and monitoring capabilities
for production deployments.
"""

import asyncio
import json
import os
import platform
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

import asyncpg

from fastjob.settings import get_settings

logger = __import__("logging").getLogger(__name__)


class WorkerHeartbeat:
    """Manages worker registration and heartbeat updates"""

    def __init__(
        self,
        pool: asyncpg.Pool,
        queues: Optional[List[str]] = None,
        concurrency: int = 1,
    ):
        self.pool = pool
        self.worker_id = uuid.uuid4()
        self.hostname = platform.node()
        self.pid = os.getpid()
        self.queues = queues or []
        self.concurrency = concurrency
        self.heartbeat_task: Optional[asyncio.Task] = None
        self.started_at = datetime.now(timezone.utc)
        self._stop_heartbeat = False

    async def register_worker(self) -> None:
        """Register this worker in the database"""
        try:
            # Get system metadata
            metadata = json.dumps(await self._get_worker_metadata())

            # Convert queues list to PostgreSQL array format
            queues_array = self.queues if self.queues else None

            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO fastjob_workers 
                    (id, hostname, pid, queues, concurrency, status, started_at, version, metadata)
                    VALUES ($1, $2, $3, $4, $5, 'active', NOW(), $6, $7)
                    ON CONFLICT (hostname, pid) 
                    DO UPDATE SET 
                        id = EXCLUDED.id,
                        queues = EXCLUDED.queues,
                        concurrency = EXCLUDED.concurrency,
                        status = 'active',
                        last_heartbeat = NOW(),
                        started_at = NOW(),
                        version = EXCLUDED.version,
                        metadata = EXCLUDED.metadata
                    """,
                    self.worker_id,
                    self.hostname,
                    self.pid,
                    queues_array,
                    self.concurrency,
                    self._get_fastjob_version(),
                    metadata,
                )

            logger.info(
                f"Worker {self.worker_id} registered on {self.hostname}:{self.pid}"
            )

        except Exception as e:
            logger.error(f"Failed to register worker: {e}")
            raise

    async def start_heartbeat(self) -> None:
        """Start the heartbeat background task"""
        if self.heartbeat_task is not None:
            return  # Already started

        settings = get_settings()
        interval = settings.worker_heartbeat_interval

        self.heartbeat_task = asyncio.create_task(self._heartbeat_loop(interval))
        logger.debug(f"Started heartbeat with {interval}s interval")

    async def stop_heartbeat(self) -> None:
        """Stop the heartbeat and mark worker as stopping"""
        self._stop_heartbeat = True

        if self.heartbeat_task:
            self.heartbeat_task.cancel()
            try:
                await self.heartbeat_task
            except asyncio.CancelledError:
                pass
            self.heartbeat_task = None

        # Mark worker as stopped
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE fastjob_workers 
                    SET status = 'stopped', last_heartbeat = NOW()
                    WHERE id = $1
                    """,
                    self.worker_id,
                )
            logger.info(f"Worker {self.worker_id} marked as stopped")
        except Exception as e:
            logger.warning(f"Failed to mark worker as stopped: {e}")

    async def update_job_worker(self, job_id: uuid.UUID) -> None:
        """Update a job to track which worker is processing it"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE fastjob_jobs SET worker_id = $1 WHERE id = $2",
                    self.worker_id,
                    job_id,
                )
        except Exception as e:
            logger.debug(f"Failed to update job worker tracking: {e}")
            # Not critical - job processing can continue

    async def _heartbeat_loop(self, interval: float) -> None:
        """Background heartbeat loop"""
        while not self._stop_heartbeat:
            try:
                await self._send_heartbeat()
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Heartbeat failed: {e}")
                from fastjob.settings import get_settings

                await asyncio.sleep(
                    min(interval, get_settings().stale_worker_threshold / 10)
                )  # Backoff but don't wait too long

    async def _send_heartbeat(self) -> None:
        """Send heartbeat update to database"""
        try:
            metadata = json.dumps(await self._get_worker_metadata())

            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE fastjob_workers 
                    SET last_heartbeat = NOW(), metadata = $2
                    WHERE id = $1
                    """,
                    self.worker_id,
                    metadata,
                )
        except Exception as e:
            logger.warning(f"Failed to send heartbeat: {e}")
            raise

    async def _get_worker_metadata(self) -> Dict[str, Any]:
        """Get current worker metadata (CPU, memory, etc.)"""
        try:
            metadata = {
                "python_version": platform.python_version(),
                "platform": platform.platform(),
                "load_avg": os.getloadavg() if hasattr(os, "getloadavg") else None,
            }

            if HAS_PSUTIL:
                process = psutil.Process(self.pid)
                metadata.update(
                    {
                        "cpu_percent": process.cpu_percent(),
                        "memory_mb": round(process.memory_info().rss / 1024 / 1024, 1),
                    }
                )
            else:
                metadata["psutil_available"] = False

            return metadata
        except Exception as e:
            logger.debug(f"Failed to get worker metadata: {e}")
            return {"error": str(e)}

    def _get_fastjob_version(self) -> str:
        """Get FastJob version"""
        try:
            import fastjob

            return getattr(fastjob, "__version__", "unknown")
        except Exception:
            return "unknown"


async def cleanup_stale_workers(
    pool: asyncpg.Pool, stale_threshold_seconds: Optional[float] = None
) -> int:
    """
    Clean up workers that haven't sent heartbeats within the threshold.

    Args:
        pool: Database connection pool
        stale_threshold_seconds: Consider workers stale after this many seconds

    Returns:
        Number of stale workers cleaned up
    """
    if stale_threshold_seconds is None:
        from fastjob.settings import get_settings

        stale_threshold_seconds = get_settings().stale_worker_threshold

    try:
        # Check if pool is closing before attempting to acquire
        if pool._closing:
            logger.debug("Pool is closing, skipping stale worker cleanup")
            return 0
            
        async with pool.acquire() as conn:
            # Mark stale workers as stopped
            result = await conn.execute(
                """
                UPDATE fastjob_workers 
                SET status = 'stopped'
                WHERE status = 'active' 
                AND last_heartbeat < NOW() - INTERVAL '%s seconds'
                """
                % stale_threshold_seconds
            )

            # Extract count from result string like "UPDATE 3"
            cleaned_count = (
                int(result.split()[-1]) if result.split()[-1].isdigit() else 0
            )

            if cleaned_count > 0:
                logger.warning(f"Marked {cleaned_count} stale workers as stopped")

            return cleaned_count

    except asyncpg.exceptions.InterfaceError as e:
        if "pool is closing" in str(e):
            logger.debug("Pool is closing, skipping stale worker cleanup")
            return 0
        logger.error(f"Failed to cleanup stale workers: {e}")
        return 0
    except Exception as e:
        logger.error(f"Failed to cleanup stale workers: {e}")
        return 0


async def get_worker_status(pool: asyncpg.Pool) -> Dict[str, Any]:
    """
    Get current worker status for monitoring.

    Returns:
        Dictionary with worker statistics and status information
    """
    try:
        async with pool.acquire() as conn:
            # Get worker counts by status
            status_counts = await conn.fetch(
                "SELECT status, COUNT(*) as count FROM fastjob_workers GROUP BY status"
            )

            # Get active workers with details
            active_workers = await conn.fetch(
                """
                SELECT id, hostname, pid, queues, concurrency, last_heartbeat, started_at, metadata
                FROM fastjob_workers 
                WHERE status = 'active'
                ORDER BY last_heartbeat DESC
                """
            )

            # Calculate stale workers (no heartbeat in 5+ minutes)
            stale_workers = await conn.fetch(
                """
                SELECT id, hostname, pid, last_heartbeat
                FROM fastjob_workers 
                WHERE status = 'active' 
                AND last_heartbeat < NOW() - INTERVAL '300 seconds'
                """
            )

            return {
                "status_counts": {row["status"]: row["count"] for row in status_counts},
                "active_workers": [
                    {
                        "id": str(row["id"]),
                        "hostname": row["hostname"],
                        "pid": row["pid"],
                        "queues": row["queues"] or [],
                        "concurrency": row["concurrency"],
                        "last_heartbeat": row["last_heartbeat"].isoformat(),
                        "started_at": row["started_at"].isoformat(),
                        "uptime_seconds": (
                            datetime.now(timezone.utc)
                            - (
                                row["started_at"].replace(tzinfo=timezone.utc)
                                if row["started_at"].tzinfo is None
                                else row["started_at"]
                            )
                        ).total_seconds(),
                        "metadata": row["metadata"],
                    }
                    for row in active_workers
                ],
                "stale_workers": [
                    {
                        "id": str(row["id"]),
                        "hostname": row["hostname"],
                        "pid": row["pid"],
                        "last_heartbeat": row["last_heartbeat"].isoformat(),
                        "stale_seconds": (
                            datetime.now(timezone.utc)
                            - (
                                row["last_heartbeat"].replace(tzinfo=timezone.utc)
                                if row["last_heartbeat"].tzinfo is None
                                else row["last_heartbeat"]
                            )
                        ).total_seconds(),
                    }
                    for row in stale_workers
                ],
                "total_concurrency": sum(w["concurrency"] for w in active_workers),
                "health": "healthy" if not stale_workers else "degraded",
            }

    except Exception as e:
        logger.error(f"Failed to get worker status: {e}")
        return {"error": str(e), "health": "unknown"}
