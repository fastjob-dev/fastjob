"""
FastJob Enhanced Configuration Module

Provides enhanced programmatic configuration for FastJob that works alongside
the existing Pydantic settings system, with improved validation, error handling,
and developer experience.
"""

import logging
import os
from typing import Any, Dict, Optional, Union
from urllib.parse import urlparse

from .settings import FastJobSettings, get_settings


class FastJobError(Exception):
    """Base FastJob exception"""

    pass


class FastJobConfigError(FastJobError):
    """Configuration error"""

    pass


class FastJobAlreadyConfiguredError(FastJobConfigError):
    """FastJob is already configured"""

    pass


class FastJobConfig:
    """Enhanced FastJob configuration that works with existing settings system"""

    def __init__(self):
        self._configured = False
        self._config: Dict[str, Any] = {}
        self._logger = logging.getLogger("fastjob.config")

    def configure(
        self,
        database_url: str,
        *,
        worker_concurrency: int = 4,
        job_timeout: Optional[float] = None,
        retry_delay: Optional[float] = None,
        max_retries: Optional[int] = None,
        default_queue: Optional[str] = None,
        poll_interval: Optional[float] = None,
        pool_size: Optional[int] = None,
        max_overflow: Optional[int] = None,
        pool_timeout: Optional[float] = None,
        pool_recycle: Optional[int] = None,
        log_level: Optional[str] = None,
        dev_mode: Optional[bool] = None,
        **kwargs,
    ) -> None:
        """
        Configure FastJob with database and default settings.

        This works alongside the existing Pydantic settings system,
        providing a more direct configuration API with immediate validation.

        Args:
            database_url: PostgreSQL connection string (required)
            worker_concurrency: Default number of concurrent jobs per worker (default: 4)
            job_timeout: Default job timeout in seconds (default: None)
            retry_delay: Default delay between retries in seconds (default: None)
            max_retries: Default maximum retry attempts (default: None)
            default_queue: Default queue name for jobs (default: None)
            poll_interval: Worker polling interval in seconds (default: None)
            pool_size: Database connection pool size (default: None)
            max_overflow: Additional connections beyond pool_size (default: None)
            pool_timeout: Timeout waiting for connection (default: None)
            pool_recycle: Connection recycle time in seconds (default: None)
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR) (default: None)
            dev_mode: Enable development mode features (default: None, treated as False)
            **kwargs: Additional configuration options

        Raises:
            FastJobConfigError: If configuration is invalid
            FastJobAlreadyConfiguredError: If already configured
        """
        if self._configured:
            raise FastJobAlreadyConfiguredError(
                "FastJob is already configured. Call reset_config() first to reconfigure."
            )

        # Validate database URL
        self._validate_database_url(database_url)

        # Build configuration starting with required and explicit defaults
        config = {
            "database_url": database_url,
            "worker_concurrency": worker_concurrency,  # Default: 4
            "dev_mode": (
                dev_mode if dev_mode is not None else False
            ),  # None = production mode (False)
        }

        # Add optional parameters if provided
        optional_params = {
            "job_timeout": job_timeout,
            "retry_delay": retry_delay,
            "max_retries": max_retries,
            "default_queue": default_queue,
            "poll_interval": poll_interval,
            "pool_size": pool_size,
            "max_overflow": max_overflow,
            "pool_timeout": pool_timeout,
            "pool_recycle": pool_recycle,
            "log_level": log_level,
        }

        for key, value in optional_params.items():
            if value is not None:
                config[key] = value

        # Add any additional kwargs
        for key, value in kwargs.items():
            if key not in config:
                config[key] = value

        # Validate configuration
        self._validate_config(config)

        # Store configuration
        self._config = config

        # Apply to global settings via environment variables
        self._apply_to_environment()

        # Force reload of Pydantic settings
        from .settings import reload_settings

        reload_settings()

        # Configure logging
        self._setup_logging()

        self._configured = True

        # Log successful configuration (but mask sensitive data)
        self._logger.info(
            f"FastJob configured successfully. "
            f"Database: {self._mask_url(database_url)}, "
            f"Workers: {config.get('worker_concurrency', 'default')}, "
            f"Pool: {config.get('pool_size', 'default')}"
        )

    def from_env(self) -> None:
        """
        Load configuration from environment variables.

        This method bridges our enhanced config with existing environment variable patterns.
        """
        database_url = os.getenv("FASTJOB_DATABASE_URL")
        if not database_url:
            raise FastJobConfigError(
                "FASTJOB_DATABASE_URL environment variable is required. "
                "Set it to your PostgreSQL connection string."
            )

        # Build config from environment using existing patterns
        config = {"database_url": database_url}

        # Environment variable mappings
        env_mappings = {
            "FASTJOB_DEFAULT_CONCURRENCY": ("worker_concurrency", int),
            "FASTJOB_JOB_TIMEOUT": ("job_timeout", float),
            "FASTJOB_DEFAULT_MAX_RETRIES": ("max_retries", int),
            "FASTJOB_DEFAULT_QUEUES": ("default_queue", str),
            "FASTJOB_DB_POOL_MAX_SIZE": ("pool_size", int),
            "FASTJOB_LOG_LEVEL": ("log_level", str),
            "FASTJOB_DEV_MODE": ("dev_mode", self._parse_bool),
        }

        for env_var, (config_key, type_func) in env_mappings.items():
            value = os.getenv(env_var)
            if value is not None:
                try:
                    if config_key == "default_queue" and "," in value:
                        # Handle comma-separated queues, take first one
                        config[config_key] = value.split(",")[0].strip()
                    else:
                        config[config_key] = type_func(value)
                except (ValueError, TypeError) as e:
                    raise FastJobConfigError(
                        f"Invalid value for {env_var}: '{value}'. {e}"
                    )

        # Use configure() to apply the configuration
        self.configure(**config)

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value.

        Falls back to Pydantic settings if not in our config.
        """
        if key in self._config:
            return self._config[key]

        # Try to get from Pydantic settings
        try:
            settings = get_settings()

            # Map our keys to settings field names
            settings_map = {
                "database_url": "database_url",
                "worker_concurrency": "default_concurrency",
                "job_timeout": "job_timeout",
                "max_retries": "default_max_retries",
                "default_queue": "default_queues",
                "pool_size": "db_pool_max_size",
                "log_level": "log_level",
                "dev_mode": "dev_mode",
            }

            settings_key = settings_map.get(key, key)
            if hasattr(settings, settings_key):
                value = getattr(settings, settings_key)
                # Convert list back to string for default_queue
                if key == "default_queue" and isinstance(value, list):
                    return value[0] if value else "default"
                return value
        except Exception:
            pass

        return default

    def get_all(self) -> Dict[str, Any]:
        """Get all configuration as dictionary."""
        return self._config.copy()

    def reset(self) -> None:
        """Reset configuration (mainly for testing)."""
        self._configured = False
        self._config = {}
        self._logger.debug("FastJob enhanced configuration reset")

    def is_configured(self) -> bool:
        """Check if FastJob is configured via this enhanced config."""
        return self._configured

    def _validate_database_url(self, url: str) -> None:
        """Validate database URL format"""
        if not url or not isinstance(url, str):
            raise FastJobConfigError("database_url must be a non-empty string")

        try:
            parsed = urlparse(url)
            if parsed.scheme not in ("postgresql", "postgres"):
                raise FastJobConfigError(
                    f"Unsupported database scheme: '{parsed.scheme}'. "
                    "FastJob requires PostgreSQL (postgresql:// or postgres://)."
                )

            if not parsed.netloc:
                raise FastJobConfigError(
                    "Invalid database URL: missing host/port information"
                )

        except Exception as e:
            if isinstance(e, FastJobConfigError):
                raise
            raise FastJobConfigError(f"Invalid database URL format: {e}")

    def _validate_config(self, config: Dict[str, Any]) -> None:
        """Validate configuration values"""
        validations = [
            (
                "worker_concurrency",
                lambda x: isinstance(x, int) and x >= 1,
                "worker_concurrency must be an integer >= 1",
            ),
            (
                "job_timeout",
                lambda x: isinstance(x, (int, float)) and x >= 1,
                "job_timeout must be a number >= 1",
            ),
            (
                "max_retries",
                lambda x: isinstance(x, int) and x >= 0,
                "max_retries must be an integer >= 0",
            ),
            (
                "default_queue",
                lambda x: isinstance(x, str) and len(x.strip()) > 0,
                "default_queue must be a non-empty string",
            ),
            (
                "poll_interval",
                lambda x: isinstance(x, (int, float)) and x > 0,
                "poll_interval must be a number > 0",
            ),
            (
                "pool_size",
                lambda x: isinstance(x, int) and x >= 1,
                "pool_size must be an integer >= 1",
            ),
            (
                "log_level",
                lambda x: isinstance(x, str)
                and x.upper() in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                "log_level must be one of: DEBUG, INFO, WARNING, ERROR, CRITICAL",
            ),
            ("dev_mode", lambda x: isinstance(x, bool), "dev_mode must be a boolean"),
        ]

        for key, validator, error_msg in validations:
            if key in config and not validator(config[key]):
                raise FastJobConfigError(f"{error_msg}, got: {config[key]}")

    def _apply_to_environment(self) -> None:
        """Apply configuration to environment variables for Pydantic settings"""
        # Map our config to environment variables
        env_mappings = {
            "database_url": "FASTJOB_DATABASE_URL",
            "worker_concurrency": "FASTJOB_DEFAULT_CONCURRENCY",
            "job_timeout": "FASTJOB_JOB_TIMEOUT",
            "max_retries": "FASTJOB_DEFAULT_MAX_RETRIES",
            "default_queue": "FASTJOB_DEFAULT_QUEUES",
            "pool_size": "FASTJOB_DB_POOL_MAX_SIZE",
            "log_level": "FASTJOB_LOG_LEVEL",
            "dev_mode": "FASTJOB_DEV_MODE",
        }

        for config_key, env_var in env_mappings.items():
            if config_key in self._config:
                value = self._config[config_key]
                if isinstance(value, bool):
                    os.environ[env_var] = "true" if value else "false"
                else:
                    os.environ[env_var] = str(value)

    def _setup_logging(self) -> None:
        """Setup logging configuration"""
        try:
            log_level = self._config.get("log_level", "INFO")
            level = getattr(logging, log_level.upper())
            logger = logging.getLogger("fastjob")
            logger.setLevel(level)
        except AttributeError:
            # Fallback to INFO if log level is invalid
            logging.getLogger("fastjob").setLevel(logging.INFO)

    def _mask_url(self, url: str) -> str:
        """Mask sensitive parts of database URL for logging"""
        try:
            parsed = urlparse(url)
            if parsed.password:
                masked_netloc = parsed.netloc.replace(parsed.password, "***")
                masked = parsed._replace(netloc=masked_netloc)
                return masked.geturl()
            return url
        except Exception:
            return "postgresql://***"

    def _parse_bool(self, value: str) -> bool:
        """Parse boolean from string"""
        if isinstance(value, bool):
            return value

        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes", "on", "enabled")

        return bool(value)


# Global enhanced configuration instance
_config = FastJobConfig()


# Public API functions
def configure(**kwargs) -> None:
    """
    Configure FastJob with enhanced validation and error handling.

    This is an enhanced version of FastJob configuration that provides:
    - Immediate validation with clear error messages
    - Better developer experience
    - Integration with existing Pydantic settings

    Args:
        **kwargs: Configuration parameters (see FastJobConfig.configure)

    Example:
        import fastjob

        fastjob.configure(
            database_url="postgresql://localhost/myapp",
            worker_concurrency=8,
            pool_size=30
        )
    """
    return _config.configure(**kwargs)


def get_config() -> FastJobConfig:
    """
    Get the enhanced FastJob configuration instance.

    Returns:
        FastJobConfig instance
    """
    return _config


def reset_config() -> None:
    """
    Reset enhanced FastJob configuration (mainly for testing).

    This allows reconfiguration after calling configure().
    """
    return _config.reset()


def is_configured() -> bool:
    """
    Check if FastJob is configured via enhanced config.

    Returns:
        True if configured via enhanced API, False otherwise
    """
    return _config.is_configured()


def get_setting(key: str, default: Any = None) -> Any:
    """
    Get a specific configuration setting.

    Falls back to Pydantic settings if not in enhanced config.

    Args:
        key: Setting name
        default: Default value if not found

    Returns:
        Setting value or default
    """
    return _config.get(key, default)


def get_database_url() -> str:
    """
    Get the configured database URL.

    Returns:
        Database URL string

    Raises:
        FastJobConfigError: If not configured and no environment variable
    """
    url = _config.get("database_url")
    if not url:
        # Try to get from existing settings
        try:
            settings = get_settings()
            url = settings.database_url
        except Exception:
            pass

    if not url:
        raise FastJobConfigError(
            "No database URL configured. Call fastjob.configure() or set "
            "FASTJOB_DATABASE_URL environment variable."
        )
    return url
