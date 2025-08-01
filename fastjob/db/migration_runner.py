"""
FastJob Database Migration System

A proper, versioned migration system that preserves data and allows
for safe schema evolution without data loss.
"""

import logging
from pathlib import Path
from typing import List, Tuple

import asyncpg

from .connection import get_pool

logger = logging.getLogger(__name__)


class MigrationError(Exception):
    """Raised when migration operations fail"""

    pass


class MigrationRunner:
    """Manages database schema migrations for FastJob"""

    def __init__(self, migrations_dir: Path = None):
        if migrations_dir is None:
            migrations_dir = Path(__file__).parent / "migrations"
        self.migrations_dir = migrations_dir

    async def ensure_migration_table(self, conn: asyncpg.Connection) -> None:
        """Create the migration tracking table if it doesn't exist"""
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fastjob_migrations (
                id SERIAL PRIMARY KEY,
                version VARCHAR(255) NOT NULL UNIQUE,
                name TEXT NOT NULL,
                applied_at TIMESTAMP DEFAULT NOW(),
                checksum TEXT
            )
        """
        )

        # Create index for faster lookups
        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_fastjob_migrations_version
            ON fastjob_migrations (version)
        """
        )

    def discover_migrations(self) -> List[Tuple[str, str, Path]]:
        """
        Discover all migration files in the migrations directory.

        Returns:
            List of (version, name, file_path) tuples sorted by version
        """
        migrations = []

        if not self.migrations_dir.exists():
            logger.warning(
                f"Migrations directory does not exist: {self.migrations_dir}"
            )
            return migrations

        for file_path in self.migrations_dir.glob("*.sql"):
            filename = file_path.stem

            # Expected format: "001_initial_schema" or "002_add_retry_count"
            try:
                parts = filename.split("_", 1)
                if len(parts) >= 2:
                    version = parts[0]
                    name = parts[1] if len(parts) > 1 else "unnamed"
                    migrations.append((version, name, file_path))
                else:
                    logger.warning(
                        f"Skipping migration file with invalid name format: {filename}"
                    )
            except Exception as e:
                logger.warning(f"Error parsing migration filename {filename}: {e}")

        # Sort by version (assumes version is numeric like 001, 002, etc.)
        migrations.sort(key=lambda x: x[0])
        return migrations

    async def get_applied_migrations(self, conn: asyncpg.Connection) -> List[str]:
        """Get list of migration versions that have already been applied"""
        await self.ensure_migration_table(conn)

        rows = await conn.fetch(
            """
            SELECT version FROM fastjob_migrations ORDER BY version
        """
        )

        return [row["version"] for row in rows]

    async def apply_migration(
        self, conn: asyncpg.Connection, version: str, name: str, file_path: Path
    ) -> None:
        """Apply a single migration within a transaction"""
        logger.info(f"Applying migration {version}: {name}")

        try:
            # Read migration SQL
            with open(file_path, "r", encoding="utf-8") as f:
                migration_sql = f.read()

            # Apply migration in a transaction
            async with conn.transaction():
                # Execute the migration SQL
                await conn.execute(migration_sql)

                # Record the migration as applied
                await conn.execute(
                    """
                    INSERT INTO fastjob_migrations (version, name, applied_at)
                    VALUES ($1, $2, NOW())
                """,
                    version,
                    name,
                )

            logger.info(f"Successfully applied migration {version}: {name}")

        except Exception as e:
            logger.error(f"Failed to apply migration {version}: {name} - {e}")
            raise MigrationError(f"Migration {version} failed: {e}") from e

    async def run_migrations(self, conn: asyncpg.Connection = None) -> int:
        """
        Run all pending migrations.

        Returns:
            Number of migrations applied
        """
        if conn is None:
            pool = await get_pool()
            async with pool.acquire() as conn:
                return await self._run_migrations_with_connection(conn)
        else:
            return await self._run_migrations_with_connection(conn)

    async def _run_migrations_with_connection(self, conn: asyncpg.Connection) -> int:
        """Internal method to run migrations with a provided connection"""
        logger.info("Starting database migration process")

        # Ensure migration tracking table exists
        await self.ensure_migration_table(conn)

        # Discover available migrations
        available_migrations = self.discover_migrations()
        if not available_migrations:
            logger.info("No migration files found")
            return 0

        # Get already applied migrations
        applied_migrations = await self.get_applied_migrations(conn)
        applied_set = set(applied_migrations)

        # Determine which migrations need to be applied
        pending_migrations = [
            (version, name, file_path)
            for version, name, file_path in available_migrations
            if version not in applied_set
        ]

        if not pending_migrations:
            logger.info("All migrations are up to date")
            return 0

        logger.info(f"Found {len(pending_migrations)} pending migrations")

        # Apply each pending migration
        applied_count = 0
        for version, name, file_path in pending_migrations:
            await self.apply_migration(conn, version, name, file_path)
            applied_count += 1

        logger.info(f"Successfully applied {applied_count} migrations")
        return applied_count

    async def get_migration_status(self, conn: asyncpg.Connection = None) -> dict:
        """
        Get current migration status.

        Returns:
            Dictionary with migration status information
        """
        if conn is None:
            pool = await get_pool()
            async with pool.acquire() as conn:
                return await self._get_migration_status_with_connection(conn)
        else:
            return await self._get_migration_status_with_connection(conn)

    async def _get_migration_status_with_connection(
        self, conn: asyncpg.Connection
    ) -> dict:
        """Internal method to get migration status with a provided connection"""
        await self.ensure_migration_table(conn)

        available_migrations = self.discover_migrations()
        applied_migrations = await self.get_applied_migrations(conn)
        applied_set = set(applied_migrations)

        pending_migrations = [
            f"{version}_{name}"
            for version, name, _ in available_migrations
            if version not in applied_set
        ]

        return {
            "total_migrations": len(available_migrations),
            "applied_migrations": applied_migrations,
            "pending_migrations": pending_migrations,
            "is_up_to_date": len(pending_migrations) == 0,
        }


# Global migration runner instance
_migration_runner = MigrationRunner()


async def run_migrations(conn: asyncpg.Connection = None) -> int:
    """
    Run all pending database migrations.

    Args:
        conn: Optional database connection. If not provided, creates one.

    Returns:
        Number of migrations applied

    Raises:
        MigrationError: If any migration fails
    """
    return await _migration_runner.run_migrations(conn)


async def get_migration_status(conn: asyncpg.Connection = None) -> dict:
    """
    Get current database migration status.

    Args:
        conn: Optional database connection. If not provided, creates one.

    Returns:
        Dictionary with migration status information
    """
    return await _migration_runner.get_migration_status(conn)
