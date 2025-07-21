"""
FastJob Configuration Management

Uses Pydantic v2 BaseSettings for robust, type-safe configuration with support for
environment variables, config files, and validation.
"""

import os
from typing import Optional, List
from pathlib import Path

from pydantic_settings import BaseSettings
from pydantic import Field, ValidationError, field_validator


class FastJobSettings(BaseSettings):
    """
    FastJob configuration with environment variable support and validation.
    
    Configuration priority:
    1. Environment variables (FASTJOB_*)
    2. Config file (if specified)
    3. Default values
    """
    
    # Database Configuration
    database_url: str = Field(
        default="postgresql://postgres@localhost/postgres",
        description="PostgreSQL database URL for FastJob"
    )
    
    # Job Discovery
    jobs_module: str = Field(
        default="jobs",
        description="Module name for automatic job discovery"
    )
    
    # Worker Configuration  
    default_concurrency: int = Field(
        default=4,
        ge=1,
        le=100,
        description="Default number of concurrent workers"
    )
    
    default_queues: List[str] = Field(
        default=["default"],
        description="Default queues to process"
    )
    
    # Job Processing Settings
    default_max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Default maximum retry attempts for failed jobs"
    )
    
    default_priority: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="Default job priority (lower = higher priority)"
    )
    
    # Timeouts and Intervals
    worker_heartbeat_interval: float = Field(
        default=5.0,
        ge=0.1,
        le=60.0,
        description="Worker heartbeat check interval in seconds"
    )
    
    job_timeout: Optional[float] = Field(
        default=None,
        ge=1.0,
        description="Default job execution timeout in seconds"
    )
    
    # Connection Pool Settings
    db_pool_min_size: int = Field(
        default=5,
        ge=1,
        le=100,
        description="Minimum database connection pool size"
    )
    
    db_pool_max_size: int = Field(
        default=20,
        ge=1,
        le=200,
        description="Maximum database connection pool size"
    )
    
    # Logging Configuration
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)"
    )
    
    log_format: str = Field(
        default="simple",
        description="Log format: 'simple' or 'structured'"
    )
    
    # Development/Testing
    debug: bool = Field(
        default=False,
        description="Enable debug mode"
    )
    
    environment: str = Field(
        default="production",
        description="Environment name (development, testing, production)"
    )
    
    model_config = {
        "env_prefix": "FASTJOB_",
        "case_sensitive": False,
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }
    
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


def get_settings(config_file: Optional[Path] = None, reload: bool = False) -> FastJobSettings:
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


# Create settings instance and provide backward compatibility
settings = get_settings()

# Backward compatibility exports
FASTJOB_DATABASE_URL = settings.database_url
FASTJOB_JOBS_MODULE = settings.jobs_module
