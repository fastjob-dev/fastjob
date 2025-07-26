"""
Test the testing utilities for controlling plugin loading
"""

# Set test database before importing fastjob modules
import os

os.environ["FASTJOB_DATABASE_URL"] = "postgresql://postgres@localhost/fastjob_test"


class TestPluginLoadingControl:
    """Test the basic plugin loading control utilities"""

    def setup_method(self):
        """Clean up plugin state before each test"""
        from fastjob.testing import reset_plugin_state

        reset_plugin_state()

    def teardown_method(self):
        """Clean up after each test"""
        from fastjob.testing import reset_plugin_state

        reset_plugin_state()

    def test_testing_utilities_basic_functionality(self):
        """Test that testing utilities have the expected basic functionality"""
        from fastjob.testing import (
            disable_plugins,
            enable_plugins,
            no_plugins,
            is_plugin_loading_disabled,
            reset_plugin_state,
        )

        # Test initial state
        assert is_plugin_loading_disabled() is False

        # Test disable
        disable_plugins()
        assert is_plugin_loading_disabled() is True

        # Test enable
        enable_plugins()
        assert is_plugin_loading_disabled() is False

        # Test context manager
        with no_plugins():
            assert is_plugin_loading_disabled() is True
        assert is_plugin_loading_disabled() is False

        # Test reset
        disable_plugins()
        assert is_plugin_loading_disabled() is True
        reset_plugin_state()
        assert is_plugin_loading_disabled() is False

    def test_context_manager_nesting(self):
        """Test that context manager works with nesting"""
        from fastjob.testing import no_plugins, is_plugin_loading_disabled

        assert is_plugin_loading_disabled() is False

        with no_plugins():
            assert is_plugin_loading_disabled() is True

            with no_plugins():
                assert is_plugin_loading_disabled() is True

            assert is_plugin_loading_disabled() is True

        assert is_plugin_loading_disabled() is False

    def test_plugin_loading_state_isolation(self):
        """Test that plugin loading state is properly isolated"""
        from fastjob.testing import (
            disable_plugins,
            enable_plugins,
            is_plugin_loading_disabled,
        )

        # Initial state
        assert is_plugin_loading_disabled() is False

        # Change state
        disable_plugins()
        assert is_plugin_loading_disabled() is True

        # Change back
        enable_plugins()
        assert is_plugin_loading_disabled() is False

    def test_fastjob_imports_work_with_testing_utilities(self):
        """Test that FastJob can be imported and basic functions work with testing utilities"""
        from fastjob.testing import disable_plugins

        disable_plugins()

        # Should be able to import and use basic FastJob functionality
        import fastjob

        # These should work without triggering plugin loading
        settings = fastjob.get_settings()
        assert settings is not None

        # Job decorator should work
        @fastjob.job()
        async def test_job():
            return "test"

        assert test_job is not None

        # Plugin utilities should work
        assert hasattr(fastjob, "load_plugins")
        assert hasattr(fastjob, "has_plugin_feature")
