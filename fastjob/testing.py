"""
FastJob Testing Utilities

Provides utilities for controlling FastJob behavior during testing,
particularly for disabling automatic plugin loading.
"""

import contextlib
from typing import Optional

# Global state for plugin loading control
_plugins_disabled = False


def disable_plugins():
    """
    Disable automatic plugin loading for testing.
    
    Call this function in test setup to prevent FastJob from automatically
    loading Pro/Enterprise plugins during test execution.
    
    Example:
        from fastjob.testing import disable_plugins
        
        def setup_method(self):
            disable_plugins()
            
        def test_core_functionality(self):
            import fastjob
            # Only core functionality available, no plugins loaded
            pass
    """
    global _plugins_disabled
    _plugins_disabled = True


def enable_plugins():
    """
    Re-enable automatic plugin loading.
    
    Call this function to restore the default behavior of automatically
    loading plugins when FastJob operations are performed.
    
    Example:
        from fastjob.testing import enable_plugins
        
        def teardown_method(self):
            enable_plugins()  # Restore default behavior
    """
    global _plugins_disabled
    _plugins_disabled = False


@contextlib.contextmanager
def no_plugins():
    """
    Context manager to temporarily disable plugin loading.
    
    Use this context manager to disable plugin loading for a specific
    block of code, then automatically restore the previous state.
    
    Example:
        from fastjob.testing import no_plugins
        
        def test_with_and_without_plugins():
            # Plugins available here
            import fastjob
            
            with no_plugins():
                # Plugins disabled in this block
                # Only core FastJob functionality available
                pass
            
            # Plugins available again here
    """
    global _plugins_disabled
    # Save the current state locally to handle nesting properly
    original_state = _plugins_disabled
    _plugins_disabled = True
    try:
        yield
    finally:
        _plugins_disabled = original_state


def is_plugin_loading_disabled():
    """
    Check if plugin loading is currently disabled.
    
    This function is used internally by FastJob to determine whether
    to automatically load plugins. It's not typically needed in user code.
    
    Returns:
        bool: True if plugin loading is disabled, False otherwise
    """
    return _plugins_disabled


def reset_plugin_state():
    """
    Reset plugin loading state to default (enabled).
    
    This function is useful in test teardown to ensure a clean state
    for subsequent tests.
    
    Example:
        from fastjob.testing import reset_plugin_state
        
        def teardown_method(self):
            reset_plugin_state()
    """
    global _plugins_disabled
    _plugins_disabled = False