"""
Comprehensive tests for FastJob's Pydantic-based configuration system.

Tests cover:
- Default configuration loading
- Environment variable overrides
- Configuration validation
- Explicit FASTJOB_DATABASE_URL requirement (no DATABASE_URL fallback)
- Pydantic availability fallback
- Configuration file loading
- get_settings() and reload_settings() functions
"""

import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Set test database before importing fastjob modules
os.environ["FASTJOB_DATABASE_URL"] = "postgresql://postgres@localhost/fastjob_test"


class TestPydanticConfiguration:
    """Test the Pydantic-based configuration system."""

    def setup_method(self):
        """Set up each test with clean environment."""
        # Store original environment
        self.original_env = {}
        for key in os.environ:
            if key.startswith('FASTJOB_'):
                self.original_env[key] = os.environ[key]

        # Clear FastJob environment variables for clean testing
        for key in list(os.environ.keys()):
            if key.startswith('FASTJOB_'):
                del os.environ[key]

        # Clear settings cache
        import fastjob.settings
        fastjob.settings._settings = None

    def teardown_method(self):
        """Clean up after each test."""
        # Restore original environment
        for key in list(os.environ.keys()):
            if key.startswith('FASTJOB_'):
                del os.environ[key]

        for key, value in self.original_env.items():
            os.environ[key] = value

        # Clear settings cache
        import fastjob.settings
        fastjob.settings._settings = None

    def test_default_configuration_loading(self):
        """Test that configuration loads correctly with default values."""
        from fastjob.settings import get_settings

        settings = get_settings()

        # Test default values
        assert settings.database_url == "postgresql://postgres@localhost/postgres"
        assert settings.jobs_module == "jobs"
        assert settings.default_concurrency == 4
        assert settings.default_queues == ["default"]
        assert settings.default_max_retries == 3
        assert settings.default_priority == 100
        assert settings.worker_heartbeat_interval == 5.0
        assert settings.job_timeout is None
        assert settings.db_pool_min_size == 5
        assert settings.db_pool_max_size == 20
        assert settings.log_level == "INFO"
        assert settings.log_format == "simple"
        assert settings.debug is False
        assert settings.environment == "production"

    def test_environment_variable_overrides(self):
        """Test environment variable override functionality."""
        # Set environment variables
        os.environ["FASTJOB_DATABASE_URL"] = "postgresql://test@localhost/test_db"
        os.environ["FASTJOB_JOBS_MODULE"] = "myapp.jobs"
        os.environ["FASTJOB_DEFAULT_CONCURRENCY"] = "8"
        os.environ["FASTJOB_DEFAULT_QUEUES"] = "urgent,default,low"
        os.environ["FASTJOB_DEFAULT_MAX_RETRIES"] = "5"
        os.environ["FASTJOB_DEFAULT_PRIORITY"] = "200"
        os.environ["FASTJOB_WORKER_HEARTBEAT_INTERVAL"] = "10.0"
        os.environ["FASTJOB_JOB_TIMEOUT"] = "300.0"
        os.environ["FASTJOB_DB_POOL_MIN_SIZE"] = "10"
        os.environ["FASTJOB_DB_POOL_MAX_SIZE"] = "50"
        os.environ["FASTJOB_LOG_LEVEL"] = "DEBUG"
        os.environ["FASTJOB_LOG_FORMAT"] = "structured"
        os.environ["FASTJOB_DEBUG"] = "true"
        os.environ["FASTJOB_ENVIRONMENT"] = "development"

        from fastjob.settings import get_settings
        settings = get_settings(reload=True)

        # Test overridden values
        assert settings.database_url == "postgresql://test@localhost/test_db"
        assert settings.jobs_module == "myapp.jobs"
        assert settings.default_concurrency == 8
        assert settings.default_queues == ["urgent", "default", "low"]
        assert settings.default_max_retries == 5
        assert settings.default_priority == 200
        assert settings.worker_heartbeat_interval == 10.0
        assert settings.job_timeout == 300.0
        assert settings.db_pool_min_size == 10
        assert settings.db_pool_max_size == 50
        assert settings.log_level == "DEBUG"
        assert settings.log_format == "structured"
        assert settings.debug is True
        assert settings.environment == "development"

    def test_configuration_validation_invalid_database_url(self):
        """Test configuration validation for invalid database URLs."""
        os.environ["FASTJOB_DATABASE_URL"] = "mysql://invalid@localhost/test"

        from fastjob.settings import get_settings

        # Should raise validation error for non-PostgreSQL URL
        with pytest.raises(ValueError, match=r"(?s)Invalid FastJob configuration.*database_url must be a PostgreSQL connection string"):
            get_settings(reload=True)

    def test_configuration_validation_invalid_log_level(self):
        """Test configuration validation for invalid log levels."""
        os.environ["FASTJOB_LOG_LEVEL"] = "INVALID"

        from fastjob.settings import get_settings

        # Should raise validation error for invalid log level
        with pytest.raises(ValueError, match=r"(?s)Invalid FastJob configuration.*log_level must be one of"):
            get_settings(reload=True)

    def test_configuration_validation_invalid_log_format(self):
        """Test configuration validation for invalid log formats."""
        os.environ["FASTJOB_LOG_FORMAT"] = "json"

        from fastjob.settings import get_settings

        # Should raise validation error for invalid log format
        with pytest.raises(ValueError, match=r"(?s)Invalid FastJob configuration.*log_format must be one of"):
            get_settings(reload=True)

    def test_configuration_validation_numeric_ranges(self):
        """Test configuration validation for numeric range constraints."""
        # Test concurrency out of range
        os.environ["FASTJOB_DEFAULT_CONCURRENCY"] = "200"  # Max is 100

        from fastjob.settings import get_settings

        with pytest.raises(ValueError, match=r"(?s)Invalid FastJob configuration"):
            get_settings(reload=True)

        # Reset and test minimum
        del os.environ["FASTJOB_DEFAULT_CONCURRENCY"]
        os.environ["FASTJOB_DEFAULT_MAX_RETRIES"] = "-1"  # Min is 0

        with pytest.raises(ValueError, match=r"(?s)Invalid FastJob configuration"):
            get_settings(reload=True)

    def test_database_url_is_not_used_as_fallback(self):
        """Test that DATABASE_URL is NOT used as fallback - only FASTJOB_DATABASE_URL."""
        # Set DATABASE_URL but not FASTJOB_DATABASE_URL
        os.environ["DATABASE_URL"] = "postgresql://should_not_be_used@localhost/legacy_db"

        # Remove FASTJOB_DATABASE_URL if it exists
        if "FASTJOB_DATABASE_URL" in os.environ:
            del os.environ["FASTJOB_DATABASE_URL"]

        from fastjob.settings import get_settings
        settings = get_settings(reload=True)

        # Should use default value, NOT the DATABASE_URL fallback
        assert settings.database_url == "postgresql://postgres@localhost/postgres"
        assert settings.database_url != "postgresql://should_not_be_used@localhost/legacy_db"

    def test_fastjob_database_url_is_used_when_set(self):
        """Test that FASTJOB_DATABASE_URL is properly used when set."""
        # Set both DATABASE_URL and FASTJOB_DATABASE_URL
        os.environ["DATABASE_URL"] = "postgresql://ignored@localhost/ignored_db"
        os.environ["FASTJOB_DATABASE_URL"] = "postgresql://fastjob_user@localhost/fastjob_db"

        from fastjob.settings import get_settings
        settings = get_settings(reload=True)

        # Only FASTJOB_DATABASE_URL should be used (DATABASE_URL ignored)
        assert settings.database_url == "postgresql://fastjob_user@localhost/fastjob_db"

    def test_configuration_file_loading(self):
        """Test configuration file loading functionality."""
        # Create temporary config file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.write("FASTJOB_DATABASE_URL=postgresql://config@localhost/config_db\n")
            f.write("FASTJOB_JOBS_MODULE=config.jobs\n")
            f.write("FASTJOB_DEFAULT_CONCURRENCY=12\n")
            f.write("FASTJOB_LOG_LEVEL=WARNING\n")
            config_file = Path(f.name)

        try:
            from fastjob.settings import get_settings
            settings = get_settings(config_file=config_file, reload=True)

            # Should load from config file
            assert settings.database_url == "postgresql://config@localhost/config_db"
            assert settings.jobs_module == "config.jobs"
            assert settings.default_concurrency == 12
            assert settings.log_level == "WARNING"

        finally:
            # Clean up
            config_file.unlink()

    def test_get_settings_caching(self):
        """Test that get_settings() properly caches settings."""
        from fastjob.settings import get_settings

        # First call
        settings1 = get_settings()

        # Second call should return same instance (cached)
        settings2 = get_settings()

        assert settings1 is settings2

    def test_get_settings_reload_functionality(self):
        """Test get_settings() reload functionality."""
        # Initial settings
        os.environ["FASTJOB_DATABASE_URL"] = "postgresql://initial@localhost/initial_db"

        from fastjob.settings import get_settings
        settings1 = get_settings(reload=True)
        assert settings1.database_url == "postgresql://initial@localhost/initial_db"

        # Change environment and reload
        os.environ["FASTJOB_DATABASE_URL"] = "postgresql://reloaded@localhost/reloaded_db"
        settings2 = get_settings(reload=True)

        # Should get new settings
        assert settings2.database_url == "postgresql://reloaded@localhost/reloaded_db"
        assert settings1 is not settings2  # Different instances after reload

    def test_reload_settings_function(self):
        """Test the standalone reload_settings() function."""
        from fastjob.settings import reload_settings

        # Set initial environment
        os.environ["FASTJOB_DATABASE_URL"] = "postgresql://before@localhost/before_db"

        settings1 = reload_settings()
        assert settings1.database_url == "postgresql://before@localhost/before_db"

        # Change environment
        os.environ["FASTJOB_DATABASE_URL"] = "postgresql://after@localhost/after_db"

        settings2 = reload_settings()
        assert settings2.database_url == "postgresql://after@localhost/after_db"

    def test_backward_compatibility_exports(self):
        """Test backward compatibility exports from settings module."""
        os.environ["FASTJOB_DATABASE_URL"] = "postgresql://export_test@localhost/export_db"
        os.environ["FASTJOB_JOBS_MODULE"] = "export.jobs"

        # Reload settings to pick up environment variables
        from fastjob.settings import get_settings
        get_settings(reload=True)

        from fastjob.settings import FASTJOB_DATABASE_URL, FASTJOB_JOBS_MODULE

        # These should be available for backward compatibility
        assert FASTJOB_DATABASE_URL == "postgresql://export_test@localhost/export_db"
        assert FASTJOB_JOBS_MODULE == "export.jobs"

    def test_case_insensitive_configuration(self):
        """Test case-insensitive configuration handling."""
        # Set case variations
        os.environ["fastjob_database_url"] = "postgresql://case@localhost/case_db"  # lowercase
        os.environ["FASTJOB_LOG_LEVEL"] = "debug"  # lowercase value should be normalized
        os.environ["FASTJOB_LOG_FORMAT"] = "STRUCTURED"  # uppercase value should be normalized

        from fastjob.settings import get_settings
        settings = get_settings(reload=True)

        # Should handle case variations properly
        assert settings.database_url == "postgresql://case@localhost/case_db"
        assert settings.log_level == "DEBUG"  # Should be normalized to uppercase
        assert settings.log_format == "structured"  # Should be normalized to lowercase

    def test_list_configuration_parsing(self):
        """Test parsing of comma-separated list configurations."""
        os.environ["FASTJOB_DEFAULT_QUEUES"] = "high,normal,low,bulk"

        from fastjob.settings import get_settings
        settings = get_settings(reload=True)

        # Should parse comma-separated values into list
        assert settings.default_queues == ["high", "normal", "low", "bulk"]

    def test_boolean_configuration_parsing(self):
        """Test parsing of boolean configurations from strings."""
        # Test various boolean representations
        test_cases = [
            ("true", True),
            ("True", True),
            ("TRUE", True),
            ("1", True),
            ("false", False),
            ("False", False),
            ("FALSE", False),
            ("0", False),
            ("", False),
        ]

        for env_value, expected in test_cases:
            os.environ["FASTJOB_DEBUG"] = env_value

            from fastjob.settings import get_settings
            settings = get_settings(reload=True)

            assert settings.debug == expected, f"Failed for env_value='{env_value}', expected={expected}, got={settings.debug}"

    def test_numeric_configuration_validation(self):
        """Test numeric configuration validation and type conversion."""
        os.environ["FASTJOB_DEFAULT_CONCURRENCY"] = "8"
        os.environ["FASTJOB_WORKER_HEARTBEAT_INTERVAL"] = "2.5"
        os.environ["FASTJOB_JOB_TIMEOUT"] = "600.0"

        from fastjob.settings import get_settings
        settings = get_settings(reload=True)

        # Should properly convert string values to correct types
        assert isinstance(settings.default_concurrency, int)
        assert settings.default_concurrency == 8
        assert isinstance(settings.worker_heartbeat_interval, float)
        assert settings.worker_heartbeat_interval == 2.5
        assert isinstance(settings.job_timeout, float)
        assert settings.job_timeout == 600.0

    def test_optional_timeout_handling(self):
        """Test handling of optional timeout configurations."""
        # Test with explicit zero (should become None)
        os.environ["FASTJOB_JOB_TIMEOUT"] = "0"

        from fastjob.settings import get_settings
        settings = get_settings(reload=True)

        # Zero timeout should be converted to None in fallback mode
        # (This behavior depends on the implementation)
        assert settings.job_timeout is None or settings.job_timeout == 0.0

        # Test with valid timeout
        os.environ["FASTJOB_JOB_TIMEOUT"] = "300"
        settings = get_settings(reload=True)

        assert settings.job_timeout == 300.0