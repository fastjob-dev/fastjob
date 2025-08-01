"""
FastJob Configuration Management

Uses Pydantic v2 BaseSettings for robust, type-safe configuration with support for
environment variables, config files, and validation.
"""

from pathlib import Path
from typing import Any, List, Optional

from pydantic import Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.sources import EnvSettingsSource


class CustomEnvSource(EnvSettingsSource):
    """Custom environment source that handles comma-separated lists without JSON parsing."""

    def prepare_field_value(
        self, field_name: str, field: Any, value: Any, value_is_complex: bool
    ) -> Any:
        """Override to handle comma-separated lists for specific fields."""
        if field_name == "default_queues" and isinstance(value, str):
            # Handle comma-separated queues without JSON parsing
            return [q.strip() for q in value.split(",") if q.strip()]
        return super().prepare_field_value(field_name, field, value, value_is_complex)


class FastJobSettings(BaseSettings):
    """
    FastJob configuration with environment variable support and validation.

    Configuration priority:
    1. Environment variables (FASTJOB_*)
    2. Config file (if specified)
    3. Default values
    """

    model_config = SettingsConfigDict(
        env_prefix="FASTJOB_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        """Use custom environment source."""
        return (
            init_settings,
            CustomEnvSource(settings_cls),
            dotenv_settings,
            file_secret_settings,
        )

    # Database Configuration
    database_url: str = Field(
        default="postgresql://postgres@localhost/postgres",
        description="PostgreSQL database URL for FastJob",
    )

    # Job Discovery
    jobs_module: str = Field(
        default="jobs", description="Module name for automatic job discovery"
    )

    # Worker Configuration
    default_concurrency: int = Field(
        default=4, ge=1, le=100, description="Default number of concurrent workers"
    )

    default_queues: List[str] = Field(
        default=["default"],
        description="Default queues to process (when not using dynamic discovery)",
    )

    # Job Processing Settings
    default_max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Default maximum retry attempts for failed jobs",
    )

    default_priority: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="Default job priority (lower = higher priority)",
    )

    # Timeouts and Intervals
    worker_heartbeat_interval: float = Field(
        default=5.0,
        ge=0.1,
        le=60.0,
        description="Worker heartbeat check interval in seconds",
    )

    job_timeout: Optional[float] = Field(
        default=None, ge=1.0, description="Default job execution timeout in seconds"
    )

    # Worker Processing Intervals
    cleanup_interval: float = Field(
        default=300.0,
        ge=10.0,
        le=3600.0,
        description="Interval for cleaning up expired jobs and stale workers (seconds)",
    )

    stale_worker_threshold: float = Field(
        default=300.0,
        ge=60.0,
        le=7200.0,
        description="Time after which workers are considered stale (seconds)",
    )

    notification_timeout: float = Field(
        default=5.0,
        ge=0.1,
        le=60.0,
        description="Timeout when waiting for job notifications (seconds)",
    )

    error_retry_delay: float = Field(
        default=5.0,
        ge=0.1,
        le=300.0,
        description="Delay before retrying after worker errors (seconds)",
    )

    # Embedded Worker Settings
    embedded_poll_interval: float = Field(
        default=0.5,
        ge=0.1,
        le=10.0,
        description="Polling interval for embedded worker (seconds)",
    )

    embedded_error_timeout: float = Field(
        default=2.0,
        ge=0.1,
        le=60.0,
        description="Error retry timeout for embedded worker (seconds)",
    )

    embedded_shutdown_timeout: float = Field(
        default=5.0,
        ge=1.0,
        le=300.0,
        description="Graceful shutdown timeout for embedded worker (seconds)",
    )

    # Health Monitoring Settings
    health_check_timeout: float = Field(
        default=5.0,
        ge=0.1,
        le=60.0,
        description="Default timeout for health checks (seconds)",
    )

    health_monitoring_interval: float = Field(
        default=30.0,
        ge=1.0,
        le=3600.0,
        description="Interval for health monitoring loops (seconds)",
    )

    health_error_retry_delay: float = Field(
        default=5.0,
        ge=0.1,
        le=300.0,
        description="Delay before retrying health checks after errors (seconds)",
    )

    # Health Check Thresholds
    stuck_jobs_threshold: int = Field(
        default=100,
        ge=1,
        le=10000,
        description="Number of stuck jobs that triggers health warning",
    )

    job_failure_rate_threshold: float = Field(
        default=50.0,
        ge=0.0,
        le=100.0,
        description="Job failure rate percentage that triggers health degradation",
    )

    memory_usage_threshold: float = Field(
        default=90.0,
        ge=50.0,
        le=99.0,
        description="Memory usage percentage that triggers health warning",
    )

    disk_usage_threshold: float = Field(
        default=90.0,
        ge=50.0,
        le=99.0,
        description="Disk usage percentage that triggers health warning",
    )

    cpu_usage_threshold: float = Field(
        default=95.0,
        ge=50.0,
        le=99.0,
        description="CPU usage percentage that triggers health warning",
    )

    # CLI and Display Settings
    default_job_display_limit: int = Field(
        default=10,
        ge=1,
        le=1000,
        description="Default number of jobs to display in CLI commands",
    )

    @field_validator("job_timeout", mode="before")
    @classmethod
    def parse_job_timeout(cls, v):
        """Parse job timeout value, converting 0 to None (no timeout)."""
        if v == "0" or v == 0:
            return None
        return v

    # Connection Pool Settings
    db_pool_min_size: int = Field(
        default=5, ge=1, le=100, description="Minimum database connection pool size"
    )

    db_pool_max_size: int = Field(
        default=20, ge=1, le=200, description="Maximum database connection pool size"
    )

    # Logging Configuration
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )

    log_format: str = Field(
        default="simple", description="Log format: 'simple' or 'structured'"
    )

    # Job Result Retention (TTL)
    result_ttl: int = Field(
        default=300,
        ge=0,
        description="Time to live for completed jobs in seconds (0=delete immediately, default=300 for 5 minutes)",
    )

    # Development/Testing
    debug: bool = Field(default=False, description="Enable debug mode")

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug(cls, v):
        """Parse debug value from environment variables, handling empty strings."""
        if isinstance(v, str):
            if v.lower() in ("", "0", "false", "f", "no", "n"):
                return False
            elif v.lower() in ("1", "true", "t", "yes", "y"):
                return True
        return v

    dev_mode: bool = Field(
        default=False,
        description="Enable development mode (starts embedded worker automatically)",
    )

    environment: str = Field(
        default="production",
        description="Environment name (development, testing, production)",
    )

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v):
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"log_level must be one of {valid_levels}")
        return v.upper()

    @field_validator("log_format")
    @classmethod
    def validate_log_format(cls, v):
        valid_formats = ["simple", "structured"]
        if v.lower() not in valid_formats:
            raise ValueError(f"log_format must be one of {valid_formats}")
        return v.lower()

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v):
        if not v.startswith(("postgresql://", "postgres://")):
            raise ValueError("database_url must be a PostgreSQL connection string")
        return v


# Global settings instance
_settings: Optional[FastJobSettings] = None


def get_settings(
    config_file: Optional[Path] = None, reload: bool = False
) -> FastJobSettings:
    """
    Get FastJob settings with caching.

    Args:
        config_file: Optional path to config file
        reload: Force reload settings from environment

    Returns:
        FastJobSettings instance
    """
    global _settings

    if _settings is None or reload:
        try:
            if config_file and config_file.exists():
                # Load settings from file if provided
                _settings = FastJobSettings(_env_file=str(config_file))
            else:
                # Load from environment variables
                _settings = FastJobSettings()

        except ValidationError as e:
            raise ValueError(f"Invalid FastJob configuration: {e}")

    return _settings


def reload_settings(config_file: Optional[Path] = None):
    """Force reload settings from environment/config file."""
    return get_settings(config_file=config_file, reload=True)


# Create settings instance
settings = get_settings()


# Development helper functions (moved from helpers.py)
def is_dev_mode() -> bool:
    """
    Check if FastJob should run in development mode.

    Development mode enables:
    - Embedded worker auto-start
    - Enhanced debugging
    - Local-friendly defaults

    Controlled by FASTJOB_DEV_MODE environment variable.

    Returns:
        bool: True if in development mode

    Examples:
        # In your app startup
        @app.on_event("startup")
        async def startup():
            if fastjob.is_dev_mode():
                fastjob.start_embedded_worker()

        # Or more explicitly
        @app.on_event("startup")
        async def startup():
            # Development: FASTJOB_DEV_MODE=true
            # Production: FASTJOB_DEV_MODE=false (default)
            if fastjob.is_dev_mode():
                fastjob.start_embedded_worker()
    """
    return get_settings().dev_mode
