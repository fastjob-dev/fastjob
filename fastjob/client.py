"""
FastJob Application Instance

Instance-based architecture to replace global state patterns.
Enables multiple isolated FastJob instances with independent configurations.
"""

import asyncio
import logging
from pathlib import Path
from typing import List, Optional

import asyncpg
import asyncpg.exceptions

from .cli.registry import CLIRegistry
from .core.registry import JobRegistry
from .errors import FastJobError
from .plugins import PluginManager
from .settings import FastJobSettings

logger = logging.getLogger(__name__)


class FastJob:
    """
    FastJob Application

    Instance-based FastJob application that manages its own database connection,
    job registry, plugin system, and configuration. Replaces global state patterns
    with clean instance-based architecture.

    Examples:
        # Basic usage
        app = FastJob(database_url="postgresql://localhost/myapp")

        # Custom configuration
        app = FastJob(
            database_url="postgresql://localhost/myapp",
            default_concurrency=8,
            result_ttl=600
        )

        # Multiple instances
        app1 = FastJob(database_url="postgresql://localhost/app1")
        app2 = FastJob(database_url="postgresql://localhost/app2")
    """

    def __init__(
        self,
        database_url: Optional[str] = None,
        config_file: Optional[Path] = None,
        **settings_overrides,
    ):
        """
        Initialize FastJob application instance.

        Args:
            database_url: PostgreSQL connection URL
            config_file: Optional configuration file path
            **settings_overrides: Override any FastJobSettings field
        """
        # Core instance state
        self._initialized = False
        self._closed = False

        # Settings with overrides
        if database_url:
            settings_overrides["database_url"] = database_url

        if config_file:
            self._settings = FastJobSettings(
                _env_file=str(config_file), **settings_overrides
            )
        else:
            self._settings = FastJobSettings(**settings_overrides)

        # Instance components (initialized lazily)
        self._pool: Optional[asyncpg.Pool] = None
        self._job_registry = JobRegistry()
        self._plugin_manager = PluginManager()
        self._cli_registry = CLIRegistry()
        self._plugins_loaded = False

        # Worker state
        self._embedded_worker_task: Optional[asyncio.Task] = None
        self._embedded_shutdown_event: Optional[asyncio.Event] = None

        logger.debug(
            f"Created FastJob instance with database: {self._settings.database_url}"
        )

    @property
    def settings(self) -> FastJobSettings:
        """Get application settings."""
        return self._settings

    @property
    def is_initialized(self) -> bool:
        """Check if app is initialized."""
        return self._initialized

    @property
    def is_closed(self) -> bool:
        """Check if app is closed."""
        return self._closed

    async def _ensure_initialized(self):
        """
        Auto-initialize FastJob on first use.

        Creates database connection pool and loads plugins automatically.
        """
        if self._initialized:
            return

        if self._closed:
            raise FastJobError(
                "Cannot use closed FastJob instance", "FASTJOB_APP_CLOSED"
            )

        try:
            logger.debug("Auto-initializing FastJob application...")

            # Create database connection pool
            self._pool = await asyncpg.create_pool(
                self._settings.database_url,
                min_size=self._settings.db_pool_min_size,
                max_size=self._settings.db_pool_max_size,
            )
            logger.debug(
                f"Created database pool (min: {self._settings.db_pool_min_size}, max: {self._settings.db_pool_max_size})"
            )

            # Load plugins if not explicitly disabled
            if not self._is_testing_mode():
                await self.load_plugins()

            self._initialized = True
            logger.debug("FastJob application initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize FastJob application: {e}")
            await self._cleanup_on_error()
            raise FastJobError(
                f"FastJob initialization failed: {e}", "FASTJOB_INIT_ERROR"
            ) from e

    async def close(self):
        """
        Close the FastJob application and cleanup resources.

        Closes database connection pool, stops embedded workers,
        and cleans up all resources.
        """
        if self._closed:
            logger.warning("FastJob already closed")
            return

        logger.info("Closing FastJob application...")

        try:
            # Stop embedded worker if running
            await self._stop_embedded_worker()

            # Close database pool
            if self._pool:
                await self._pool.close()
                self._pool = None
                logger.debug("Closed database pool")

            # Plugin manager cleanup (no explicit cleanup needed)

            self._closed = True
            self._initialized = False
            logger.info("FastJob application closed successfully")

        except Exception as e:
            logger.error(f"Error during FastJob application cleanup: {e}")
            # Continue cleanup even if errors occur
            self._closed = True
            self._initialized = False

    async def load_plugins(self):
        """Load and initialize FastJob plugins."""
        if self._plugins_loaded:
            logger.debug("Plugins already loaded")
            return

        try:
            logger.info("Loading FastJob plugins...")

            # Discover and load plugins
            self._plugin_manager.load_plugins()

            # Register plugin CLI commands
            for plugin_name, plugin in self._plugin_manager.loaded_plugins.items():
                if hasattr(plugin, "register_cli_commands"):
                    plugin.register_cli_commands(self._cli_registry)
                    logger.debug(f"Registered CLI commands for plugin: {plugin_name}")

            self._plugins_loaded = True
            logger.info(f"Loaded {len(self._plugin_manager.loaded_plugins)} plugins")

        except Exception as e:
            logger.error(f"Failed to load plugins: {e}")
            raise FastJobError(
                f"Plugin loading failed: {e}", "FASTJOB_PLUGIN_ERROR"
            ) from e

    def job(self, **kwargs):
        """
        Job decorator for this FastJob instance.

        Args:
            **kwargs: Job configuration options

        Returns:
            Job decorator function
        """

        def decorator(func):
            return self._job_registry.register_job(func, **kwargs)

        return decorator

    async def enqueue(self, job_func, **kwargs):
        """
        Enqueue a job for processing.

        Args:
            job_func: Job function to enqueue
            **kwargs: Job arguments and options

        Returns:
            Job UUID
        """
        await self._ensure_initialized()

        # Import here to avoid circular dependencies
        from .core.queue import enqueue_job

        return await enqueue_job(self._pool, self._job_registry, job_func, **kwargs)

    async def schedule(self, job_func, run_at, **kwargs):
        """
        Schedule a job for future execution.

        Args:
            job_func: Job function to schedule
            run_at: When to run the job (datetime)
            **kwargs: Job arguments and options

        Returns:
            Job UUID
        """
        return await self.enqueue(job_func, scheduled_at=run_at, **kwargs)

    async def get_pool(self) -> asyncpg.Pool:
        """Get database connection pool."""
        await self._ensure_initialized()
        return self._pool

    def get_job_registry(self) -> JobRegistry:
        """Get job registry."""
        return self._job_registry

    def get_plugin_manager(self) -> PluginManager:
        """Get plugin manager."""
        return self._plugin_manager

    def get_cli_registry(self) -> CLIRegistry:
        """Get CLI registry."""
        return self._cli_registry

    async def run_worker(
        self,
        concurrency: int = 4,
        run_once: bool = False,
        queues: Optional[List[str]] = None,
    ):
        """
        Run a worker for this FastJob instance.

        Runs a worker that processes jobs using this instance's job registry,
        enabling isolated job processing with instance-based architecture.

        Args:
            concurrency: Number of concurrent job processing tasks
            run_once: If True, process available jobs once and exit
            queues: List of queue names to process. None means all queues.

        Example:
            app = FastJob(database_url="postgresql://localhost/myapp")
            await app.run_worker(concurrency=2, queues=["high", "default"])
        """
        await self._ensure_initialized()

        queue_info = "all queues" if queues is None else f"queues: {queues}"
        logger.info(
            f"Starting FastJob worker - concurrency: {concurrency}, processing: {queue_info}"
        )

        try:
            if run_once:
                return await self._run_worker_once(queues)
            else:
                return await self._run_worker_continuous(concurrency, queues)
        finally:
            logger.info("FastJob worker stopped")

    async def _run_worker_once(self, queues: Optional[List[str]] = None) -> bool:
        """
        Process all available jobs once and exit.

        Continues processing until no more jobs are available,
        allowing for retries and full queue draining.

        Returns:
            True if any jobs were processed, False otherwise
        """
        from .core.processor import process_jobs_with_registry

        jobs_processed = False

        # Keep processing until no more jobs are available
        while True:
            async with self._pool.acquire() as conn:
                processed = await process_jobs_with_registry(
                    conn=conn,
                    job_registry=self._job_registry,
                    queue=queues,
                    heartbeat=None,  # No heartbeat for run_once
                )

            if processed:
                jobs_processed = True
            else:
                # No more jobs available, exit
                break

        return jobs_processed

    async def _run_worker_continuous(
        self, concurrency: int, queues: Optional[List[str]] = None
    ) -> bool:
        """
        Run continuous worker with heartbeat and signal handling.

        Returns:
            True if any jobs were processed during the session
        """
        from .core.heartbeat import WorkerHeartbeat
        from .core.processor import process_jobs_with_registry
        from .utils.signals import GracefulSignalHandler

        # Create worker heartbeat system
        heartbeat = WorkerHeartbeat(self._pool, queues, concurrency)
        await heartbeat.register_worker()
        await heartbeat.start_heartbeat()

        # Continuous processing with LISTEN/NOTIFY
        async def worker():
            # Each worker needs its own connection for LISTEN/NOTIFY
            listen_conn = await self._pool.acquire()
            notification_event = asyncio.Event()

            def notification_callback(connection, pid, channel, payload):
                logger.debug(f"Received notification on {channel}: {payload}")
                notification_event.set()

            try:
                # Set up LISTEN for job notifications
                await listen_conn.add_listener("fastjob_new_job", notification_callback)

                # Track last cleanup time for periodic cleanup
                last_cleanup = 0
                cleanup_interval = self._settings.cleanup_interval

                while True:
                    try:
                        # Check if shutdown has been requested
                        if shutdown_event.is_set():
                            logger.info("Shutdown requested, stopping worker")
                            break

                        # Process jobs from all queues first
                        any_processed = False

                        # Use separate connection for job processing to avoid blocking LISTEN
                        try:
                            async with self._pool.acquire() as job_conn:
                                # Process jobs efficiently
                                processed = await process_jobs_with_registry(
                                    conn=job_conn,
                                    job_registry=self._job_registry,
                                    queue=queues,
                                    heartbeat=heartbeat,
                                )
                                if processed:
                                    any_processed = True

                                # Run periodic cleanup of expired jobs
                                import time

                                current_time = time.time()
                                if current_time - last_cleanup > cleanup_interval:
                                    try:
                                        # Clean up expired completed jobs if RESULT_TTL is set
                                        if self._settings.result_ttl > 0:
                                            cleaned = await job_conn.execute(
                                                "DELETE FROM fastjob_jobs WHERE status = 'done' AND expires_at < NOW()"
                                            )
                                            cleaned_count = (
                                                int(cleaned.split()[-1])
                                                if cleaned
                                                else 0
                                            )
                                            if cleaned_count > 0:
                                                logger.debug(
                                                    f"Cleaned up {cleaned_count} expired jobs"
                                                )

                                        # Clean up stale workers
                                        from .core.heartbeat import (
                                            cleanup_stale_workers,
                                        )

                                        await cleanup_stale_workers(
                                            self._pool,
                                            stale_threshold_seconds=self._settings.stale_worker_threshold,
                                        )

                                        last_cleanup = current_time
                                    except Exception as cleanup_error:
                                        logger.warning(
                                            f"Cleanup failed: {cleanup_error}"
                                        )
                                        last_cleanup = (
                                            current_time  # Prevent continuous retries
                                        )

                        except Exception as e:
                            if "pool is closing" in str(e):
                                logger.debug("Pool is closing, stopping worker")
                                break
                            else:
                                raise

                        if not any_processed:
                            # No jobs available, wait for NOTIFY with timeout
                            try:
                                # Wait for notification with configurable timeout
                                await asyncio.wait_for(
                                    notification_event.wait(),
                                    timeout=self._settings.notification_timeout,
                                )
                                notification_event.clear()  # Reset for next notification
                                logger.info("Received job notification")
                            except asyncio.TimeoutError:
                                # Timeout is normal - allows periodic checks for scheduled jobs
                                logger.debug(
                                    "No notifications, checking for scheduled jobs"
                                )

                    except Exception as e:
                        logger.exception(f"Worker error: {e}")
                        await asyncio.sleep(self._settings.error_retry_delay)

            finally:
                try:
                    await listen_conn.remove_listener(
                        "fastjob_new_job", notification_callback
                    )
                except asyncpg.exceptions.InterfaceError as e:
                    logger.debug(f"Failed to remove listener (pool closing): {e}")

                try:
                    await self._pool.release(listen_conn)
                except asyncpg.exceptions.InterfaceError as e:
                    logger.debug(f"Failed to release connection (pool closing): {e}")

        # Setup signal handlers for graceful shutdown
        shutdown_event = asyncio.Event()
        signal_handler = GracefulSignalHandler()
        signal_handler.setup_signal_handlers(shutdown_event)

        # Start multiple worker tasks for concurrency
        tasks = [asyncio.create_task(worker()) for _ in range(concurrency)]

        try:
            # Create a task that waits for shutdown signal
            shutdown_task = asyncio.create_task(shutdown_event.wait())
            worker_task = asyncio.gather(*tasks, return_exceptions=True)

            # Wait for either workers to complete or shutdown signal
            done, pending = await asyncio.wait(
                [worker_task, shutdown_task], return_when=asyncio.FIRST_COMPLETED
            )

            # If shutdown was requested, cancel workers
            if shutdown_task in done:
                logger.info("Graceful shutdown initiated by signal...")
                for task in tasks:
                    if not task.done():
                        task.cancel()

                # Wait for workers to finish gracefully
                await asyncio.gather(*tasks, return_exceptions=True)

            # Cancel pending tasks
            for task in pending:
                task.cancel()

        except KeyboardInterrupt:
            # Fallback handler for direct KeyboardInterrupt (shouldn't happen with signals)
            logger.info("Shutting down workers...")
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            # Cleanup signal handlers
            signal_handler.restore_signal_handlers()

            # Stop heartbeat system
            await heartbeat.stop_heartbeat()

        return True  # Jobs may have been processed during the session

    # Job Management API

    async def get_job_status(self, job_id: str):
        """
        Get status information for a specific job.

        Args:
            job_id: UUID of the job to check

        Returns:
            Dict with job information or None if job not found
        """
        await self._ensure_initialized()

        import json
        import uuid

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, job_name, args, status, attempts, max_attempts,
                       queue, priority, scheduled_at, last_error,
                       created_at, updated_at
                FROM fastjob_jobs
                WHERE id = $1
            """,
                uuid.UUID(job_id),
            )

            if not row:
                return None

            return {
                "id": str(row["id"]),
                "job_name": row["job_name"],
                "args": json.loads(row["args"]),
                "status": row["status"],
                "attempts": row["attempts"],
                "max_attempts": row["max_attempts"],
                "queue": row["queue"],
                "priority": row["priority"],
                "scheduled_at": (
                    row["scheduled_at"].isoformat() if row["scheduled_at"] else None
                ),
                "last_error": row["last_error"],
                "created_at": row["created_at"].isoformat(),
                "updated_at": row["updated_at"].isoformat(),
            }

    async def cancel_job(self, job_id: str):
        """
        Cancel a queued job.

        Args:
            job_id: UUID of the job to cancel

        Returns:
            True if job was cancelled, False if job wasn't found or already processed
        """
        await self._ensure_initialized()

        import uuid

        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE fastjob_jobs
                SET status = 'cancelled', updated_at = NOW()
                WHERE id = $1 AND status = 'queued'
            """,
                uuid.UUID(job_id),
            )

            # Check if any rows were affected
            return result.split()[-1] == "1" if result else False

    async def retry_job(self, job_id: str):
        """
        Retry a failed job.

        Args:
            job_id: UUID of the job to retry

        Returns:
            True if job was queued for retry, False if job wasn't found or can't be retried
        """
        await self._ensure_initialized()

        import uuid

        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE fastjob_jobs
                SET status = 'queued', attempts = 0, last_error = NULL, updated_at = NOW()
                WHERE id = $1 AND status IN ('dead_letter', 'failed')
            """,
                uuid.UUID(job_id),
            )

            # Check if any rows were affected
            return result.split()[-1] == "1" if result else False

    async def delete_job(self, job_id: str):
        """
        Delete a job from the queue.

        Args:
            job_id: UUID of the job to delete

        Returns:
            True if job was deleted, False if job wasn't found
        """
        await self._ensure_initialized()

        import uuid

        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM fastjob_jobs WHERE id = $1",
                uuid.UUID(job_id),
            )

            # Check if any rows were affected
            return result.split()[-1] == "1" if result else False

    async def list_jobs(
        self, queue: str = None, status: str = None, limit: int = 100, offset: int = 0
    ):
        """
        List jobs with optional filtering.

        Args:
            queue: Filter by queue name
            status: Filter by job status
            limit: Maximum number of jobs to return
            offset: Number of jobs to skip

        Returns:
            List of job dictionaries
        """
        await self._ensure_initialized()

        import json

        # Build the query dynamically based on filters
        conditions = []
        params = []
        param_count = 0

        if queue is not None:
            param_count += 1
            conditions.append(f"queue = ${param_count}")
            params.append(queue)

        if status is not None:
            param_count += 1
            conditions.append(f"status = ${param_count}")
            params.append(status)

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        param_count += 1
        limit_param = f"${param_count}"
        params.append(limit)

        param_count += 1
        offset_param = f"${param_count}"
        params.append(offset)

        query = f"""
            SELECT id, job_name, args, status, attempts, max_attempts,
                   queue, priority, scheduled_at, last_error,
                   created_at, updated_at
            FROM fastjob_jobs
            {where_clause}
            ORDER BY created_at DESC
            LIMIT {limit_param} OFFSET {offset_param}
        """

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

            return [
                {
                    "id": str(row["id"]),
                    "job_name": row["job_name"],
                    "args": json.loads(row["args"]),
                    "status": row["status"],
                    "attempts": row["attempts"],
                    "max_attempts": row["max_attempts"],
                    "queue": row["queue"],
                    "priority": row["priority"],
                    "scheduled_at": (
                        row["scheduled_at"].isoformat() if row["scheduled_at"] else None
                    ),
                    "last_error": row["last_error"],
                    "created_at": row["created_at"].isoformat(),
                    "updated_at": row["updated_at"].isoformat(),
                }
                for row in rows
            ]

    async def get_queue_stats(self):
        """
        Get statistics for all queues.

        Returns:
            List of dictionaries with queue statistics
        """
        await self._ensure_initialized()

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    queue,
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE status = 'queued') as queued,
                    COUNT(*) FILTER (WHERE status = 'processing') as processing,
                    COUNT(*) FILTER (WHERE status = 'done') as done,
                    COUNT(*) FILTER (WHERE status = 'dead_letter') as dead_letter,
                    COUNT(*) FILTER (WHERE status = 'cancelled') as cancelled
                FROM fastjob_jobs
                GROUP BY queue
                ORDER BY queue
            """
            )

            return [
                {
                    "queue": row["queue"],
                    "total": row["total"],
                    "queued": row["queued"],
                    "processing": row["processing"],
                    "done": row["done"],
                    "dead_letter": row["dead_letter"],
                    "cancelled": row["cancelled"],
                }
                for row in rows
            ]

    async def get_migration_status(self) -> dict:
        """
        Get current database migration status for this instance.

        Returns:
            Dictionary with migration status information
        """
        await self._ensure_initialized()

        # Use the migration runner with our instance's connection pool
        from .db.migration_runner import MigrationRunner

        migration_runner = MigrationRunner()
        async with self._pool.acquire() as conn:
            return await migration_runner._get_migration_status_with_connection(conn)

    async def run_migrations(self) -> int:
        """
        Run all pending database migrations for this instance.

        Returns:
            Number of migrations applied

        Raises:
            MigrationError: If any migration fails
        """
        await self._ensure_initialized()

        # Use the migration runner with our instance's connection pool
        from .db.migration_runner import MigrationRunner

        migration_runner = MigrationRunner()
        async with self._pool.acquire() as conn:
            return await migration_runner._run_migrations_with_connection(conn)

    def _is_testing_mode(self) -> bool:
        """Check if we're in testing mode."""
        # Import here to avoid circular dependencies
        try:
            from .testing import is_plugins_disabled

            return is_plugins_disabled()
        except ImportError:
            return False

    async def _stop_embedded_worker(self):
        """Stop embedded worker if running."""
        if self._embedded_worker_task and not self._embedded_worker_task.done():
            logger.debug("Stopping embedded worker...")

            if self._embedded_shutdown_event:
                self._embedded_shutdown_event.set()

            self._embedded_worker_task.cancel()

            try:
                await asyncio.wait_for(self._embedded_worker_task, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

            self._embedded_worker_task = None
            self._embedded_shutdown_event = None
            logger.debug("Embedded worker stopped")

    async def _cleanup_on_error(self):
        """Cleanup resources after initialization error."""
        try:
            if self._pool:
                await self._pool.close()
                self._pool = None
        except Exception as e:
            logger.debug(f"Error during cleanup: {e}")
