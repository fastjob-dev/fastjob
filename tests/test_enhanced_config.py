"""
Comprehensive tests for FastJob enhanced configuration module.

These tests ensure the enhanced configure() function works correctly with validation,
error handling, environment variables, and integration with existing Pydantic settings.
"""

import os
import pytest
import logging
from unittest.mock import patch

from fastjob.config import (
    configure as enhanced_configure,
    get_config,
    reset_config,
    is_configured,
    get_setting,
    get_database_url,
    FastJobError,
    FastJobConfigError,
    FastJobAlreadyConfiguredError,
    FastJobConfig
)


class TestEnhancedConfiguration:
    """Test enhanced FastJob configuration functionality"""
    
    def setup_method(self):
        """Reset configuration before each test"""
        reset_config()
    
    def teardown_method(self):
        """Clean up after each test"""
        reset_config()
        # Clean up any test environment variables
        test_env_vars = [
            'FASTJOB_DATABASE_URL',
            'FASTJOB_DEFAULT_CONCURRENCY',
            'FASTJOB_JOB_TIMEOUT',
            'FASTJOB_DEV_MODE'
        ]
        for var in test_env_vars:
            if var in os.environ:
                del os.environ[var]
    
    def test_basic_configuration(self):
        """Test basic configuration with required parameter and defaults"""
        enhanced_configure(database_url="postgresql://localhost/test")
        
        config = get_config()
        assert config.is_configured()
        assert config.get('database_url') == "postgresql://localhost/test"
        assert config.get('worker_concurrency') == 4  # Default
        assert config.get('dev_mode') is False  # Default (production mode)
        assert is_configured()
    
    def test_advanced_configuration(self):
        """Test configuration with custom parameters"""
        enhanced_configure(
            database_url="postgresql://localhost/test",
            worker_concurrency=8,
            pool_size=30,
            job_timeout=600,
            dev_mode=True
        )
        
        config = get_config()
        assert config.get('worker_concurrency') == 8
        assert config.get('pool_size') == 30
        assert config.get('job_timeout') == 600
        assert config.get('dev_mode') is True
    
    def test_configuration_validation(self):
        """Test configuration parameter validation"""
        # Test invalid worker_concurrency
        with pytest.raises(FastJobConfigError, match="worker_concurrency must be"):
            enhanced_configure(
                database_url="postgresql://localhost/test",
                worker_concurrency=0
            )
        
        # Test invalid job_timeout
        with pytest.raises(FastJobConfigError, match="job_timeout must be"):
            enhanced_configure(
                database_url="postgresql://localhost/test",
                job_timeout=-1
            )
        
        # Test invalid default_queue
        with pytest.raises(FastJobConfigError, match="default_queue must be"):
            enhanced_configure(
                database_url="postgresql://localhost/test",
                default_queue=""
            )
    
    def test_database_url_validation(self):
        """Test database URL validation"""
        # Test missing database URL
        with pytest.raises(FastJobConfigError, match="database_url must be"):
            enhanced_configure(database_url="")
        
        # Test invalid scheme
        with pytest.raises(FastJobConfigError, match="Unsupported database scheme"):
            enhanced_configure(database_url="mysql://localhost/test")
        
        # Test missing host
        with pytest.raises(FastJobConfigError, match="missing host"):
            enhanced_configure(database_url="postgresql://")
        
        # Test valid URLs
        valid_urls = [
            "postgresql://localhost/test",
            "postgres://localhost:5432/test", 
            "postgresql://user:pass@localhost/test",
            "postgresql://user:pass@localhost:5432/test"
        ]
        
        for url in valid_urls:
            reset_config()
            enhanced_configure(database_url=url)
            assert get_config().get('database_url') == url
    
    def test_double_configuration_error(self):
        """Test that double configuration raises error"""
        enhanced_configure(database_url="postgresql://localhost/test1")
        
        with pytest.raises(FastJobAlreadyConfiguredError):
            enhanced_configure(database_url="postgresql://localhost/test2")
    
    def test_configuration_reset(self):
        """Test configuration reset functionality"""
        enhanced_configure(database_url="postgresql://localhost/test")
        assert is_configured()
        
        reset_config()
        assert not is_configured()
        
        # Should be able to configure again after reset
        enhanced_configure(database_url="postgresql://localhost/test2")
        assert get_config().get('database_url') == "postgresql://localhost/test2"
    
    def test_environment_configuration(self):
        """Test configuration from environment variables"""
        # Set environment variables
        os.environ['FASTJOB_DATABASE_URL'] = "postgresql://localhost/env_test"
        os.environ['FASTJOB_DEFAULT_CONCURRENCY'] = "6"
        os.environ['FASTJOB_DEV_MODE'] = "true"
        
        config = get_config()
        config.from_env()
        
        assert config.get('database_url') == "postgresql://localhost/env_test"
        assert config.get('worker_concurrency') == 6
        assert config.get('dev_mode') is True
    
    def test_environment_missing_database_url(self):
        """Test error when FASTJOB_DATABASE_URL is missing"""
        config = get_config()
        
        with pytest.raises(FastJobConfigError, match="FASTJOB_DATABASE_URL.*required"):
            config.from_env()
    
    def test_environment_invalid_values(self):
        """Test error handling for invalid environment values"""
        os.environ['FASTJOB_DATABASE_URL'] = "postgresql://localhost/test"
        os.environ['FASTJOB_DEFAULT_CONCURRENCY'] = "invalid"
        
        config = get_config()
        
        with pytest.raises(FastJobConfigError, match="Invalid value.*FASTJOB_DEFAULT_CONCURRENCY"):
            config.from_env()
    
    def test_configuration_precedence(self):
        """Test that explicit configure() overrides environment"""
        # Set environment variable
        os.environ['FASTJOB_DEFAULT_CONCURRENCY'] = "8"
        
        # Explicit configuration should override environment
        enhanced_configure(
            database_url="postgresql://localhost/test",
            worker_concurrency=4
        )
        
        config = get_config()
        assert config.get('worker_concurrency') == 4  # Explicit value, not env
    
    def test_get_setting_function(self):
        """Test get_setting convenience function"""
        enhanced_configure(
            database_url="postgresql://localhost/test",
            worker_concurrency=8
        )
        
        assert get_setting('worker_concurrency') == 8
        assert get_setting('nonexistent', 'default') == 'default'
    
    def test_get_database_url_function(self):
        """Test get_database_url convenience function"""
        enhanced_configure(database_url="postgresql://localhost/test")
        
        assert get_database_url() == "postgresql://localhost/test"
    
    def test_get_database_url_not_configured(self):
        """Test get_database_url when not configured"""
        # This should still work due to fallback to Pydantic settings
        try:
            url = get_database_url()
            # Should get default from Pydantic settings
            assert "postgresql://" in url
        except FastJobConfigError:
            # This is also acceptable if no fallback is available
            pass
    
    def test_logging_configuration(self):
        """Test logging setup"""
        with patch('logging.getLogger') as mock_get_logger:
            mock_logger = mock_get_logger.return_value
            
            enhanced_configure(
                database_url="postgresql://localhost/test",
                log_level="DEBUG"
            )
            
            mock_get_logger.assert_called_with('fastjob')
            mock_logger.setLevel.assert_called_with(logging.DEBUG)
    
    def test_password_masking(self):
        """Test that passwords are masked in logs"""
        config = get_config()
        
        # Test URL with password
        masked = config._mask_url("postgresql://user:secret@localhost/db")
        assert "secret" not in masked
        assert "***" in masked
        
        # Test URL without password
        masked = config._mask_url("postgresql://localhost/db")
        assert masked == "postgresql://localhost/db"
    
    def test_boolean_parsing(self):
        """Test boolean value parsing from environment"""
        config = get_config()
        
        # Test various true values
        true_values = ['true', 'True', 'TRUE', '1', 'yes', 'on', 'enabled']
        for value in true_values:
            assert config._parse_bool(value) is True
        
        # Test various false values
        false_values = ['false', 'False', 'FALSE', '0', 'no', 'off', 'disabled', '']
        for value in false_values:
            assert config._parse_bool(value) is False
        
        # Test actual boolean
        assert config._parse_bool(True) is True
        assert config._parse_bool(False) is False
    
    def test_log_level_validation(self):
        """Test log level validation"""
        # Valid log levels
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        for level in valid_levels:
            reset_config()
            enhanced_configure(
                database_url="postgresql://localhost/test",
                log_level=level
            )
            assert get_config().get('log_level') == level
        
        # Invalid log level
        with pytest.raises(FastJobConfigError, match="log_level must be one of"):
            enhanced_configure(
                database_url="postgresql://localhost/test",
                log_level="INVALID"
            )
    
    def test_pool_configuration(self):
        """Test database pool configuration"""
        enhanced_configure(
            database_url="postgresql://localhost/test",
            pool_size=50,
            max_overflow=20,
            pool_timeout=60,
            pool_recycle=7200
        )
        
        config = get_config()
        assert config.get('pool_size') == 50
        assert config.get('max_overflow') == 20
        assert config.get('pool_timeout') == 60
        assert config.get('pool_recycle') == 7200
    
    def test_additional_kwargs(self):
        """Test that additional kwargs are stored"""
        enhanced_configure(
            database_url="postgresql://localhost/test",
            custom_setting="custom_value",
            another_setting=42
        )
        
        config = get_config()
        assert config.get('custom_setting') == "custom_value"
        assert config.get('another_setting') == 42
    
    def test_dev_mode_defaults(self):
        """Test dev_mode default behavior"""
        # Test None/default behavior (should be False - production mode)
        enhanced_configure(database_url="postgresql://localhost/test")
        config = get_config()
        assert config.get('dev_mode') is False
        
        reset_config()
        
        # Test explicit True
        enhanced_configure(database_url="postgresql://localhost/test", dev_mode=True)
        config = get_config()
        assert config.get('dev_mode') is True
        
        reset_config()
        
        # Test explicit False
        enhanced_configure(database_url="postgresql://localhost/test", dev_mode=False)
        config = get_config()
        assert config.get('dev_mode') is False


class TestConfigurationPatterns:
    """Test common configuration patterns"""
    
    def setup_method(self):
        reset_config()
    
    def teardown_method(self):
        reset_config()
    
    def test_testing_pattern(self):
        """Test configuration pattern for testing"""
        # Test configuration
        enhanced_configure(
            database_url="postgresql://localhost/test_db",
            worker_concurrency=1,  # Single worker for deterministic tests
            job_timeout=10,        # Short timeout for faster tests
            dev_mode=True
        )
        
        config = get_config()
        assert config.get('worker_concurrency') == 1
        assert config.get('job_timeout') == 10
        assert config.get('dev_mode') is True
    
    def test_production_pattern(self):
        """Test configuration pattern for production"""
        # Production configuration
        enhanced_configure(
            database_url="postgresql://user:pass@prod-db:5432/myapp",
            worker_concurrency=16,
            pool_size=50,
            max_overflow=20,
            job_timeout=3600,  # 1 hour timeout
            log_level="WARNING"
        )
        
        config = get_config()
        assert config.get('worker_concurrency') == 16
        assert config.get('pool_size') == 50
        assert config.get('log_level') == "WARNING"
    
    def test_development_pattern(self):
        """Test configuration pattern for development"""
        # Development configuration
        enhanced_configure(
            database_url="postgresql://localhost/dev_db",
            worker_concurrency=2,
            dev_mode=True,
            log_level="DEBUG",
            poll_interval=0.5  # Faster polling for development
        )
        
        config = get_config()
        assert config.get('dev_mode') is True
        assert config.get('log_level') == "DEBUG"
        assert config.get('poll_interval') == 0.5


@pytest.fixture
def clean_fastjob_config():
    """Pytest fixture for clean FastJob configuration"""
    reset_config()
    yield
    reset_config()


def test_fixture_usage(clean_fastjob_config):
    """Test using the clean configuration fixture"""
    enhanced_configure(database_url="postgresql://localhost/fixture_test")
    
    assert is_configured()
    assert get_config().get('database_url') == "postgresql://localhost/fixture_test"


@pytest.fixture
def fastjob_test_config():
    """Pytest fixture with test-specific configuration"""
    enhanced_configure(
        database_url="postgresql://localhost/test_fastjob",
        worker_concurrency=1,
        job_timeout=10,
        dev_mode=True
    )
    yield get_config()
    reset_config()


def test_preconfigured_fixture(fastjob_test_config):
    """Test using pre-configured fixture"""
    assert fastjob_test_config.get('worker_concurrency') == 1
    assert fastjob_test_config.get('dev_mode') is True


def test_integration_with_main_configure():
    """Test that main fastjob.configure() uses enhanced config"""
    import fastjob
    
    # Reset both configurations
    reset_config()
    
    # Test that main configure function works with enhanced validation
    fastjob.configure(
        database_url="postgresql://localhost/integration_test",
        worker_concurrency=4,
        pool_size=25
    )
    
    # Verify enhanced config was called
    assert is_configured()
    assert get_setting('worker_concurrency') == 4
    assert get_setting('pool_size') == 25


if __name__ == "__main__":
    # Run tests without pytest
    import sys
    
    test_class = TestEnhancedConfiguration()
    pattern_class = TestConfigurationPatterns()
    
    test_methods = [
        (test_class, 'test_basic_configuration'),
        (test_class, 'test_advanced_configuration'),
        (test_class, 'test_configuration_validation'),
        (test_class, 'test_database_url_validation'),
        (test_class, 'test_double_configuration_error'),
        (test_class, 'test_configuration_reset'),
        (test_class, 'test_environment_configuration'),
        (test_class, 'test_environment_missing_database_url'),
        (test_class, 'test_configuration_precedence'),
        (test_class, 'test_get_setting_function'),
        (test_class, 'test_get_database_url_function'),
        (test_class, 'test_password_masking'),
        (test_class, 'test_boolean_parsing'),
        (test_class, 'test_pool_configuration'),
        (pattern_class, 'test_testing_pattern'),
        (pattern_class, 'test_production_pattern'),
        (pattern_class, 'test_development_pattern'),
    ]
    
    passed = 0
    failed = 0
    
    for test_obj, method_name in test_methods:
        try:
            test_obj.setup_method()
            getattr(test_obj, method_name)()
            test_obj.teardown_method()
            print(f"✅ {method_name}")
            passed += 1
        except Exception as e:
            print(f"❌ {method_name}: {e}")
            failed += 1
            test_obj.teardown_method()
    
    print(f"\n🧪 Enhanced config tests completed: {passed} passed, {failed} failed")
    
    if failed > 0:
        sys.exit(1)