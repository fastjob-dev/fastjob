"""
FastJob Plugin System

Provides a clean plugin architecture for Pro and Enterprise features.
"""

import importlib
import importlib.metadata
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)

# Global plugin registry
_plugins: Dict[str, Any] = {}
_plugin_hooks: Dict[str, List[Any]] = {}


class PluginManager:
    """Manages FastJob plugins using entry points."""
    
    def __init__(self):
        self.loaded_plugins = {}
        self.hooks = {}
    
    def discover_plugins(self) -> Dict[str, Any]:
        """Discover all FastJob plugins using entry points."""
        plugins = {}
        
        try:
            # Discover plugins through entry points
            entry_points = importlib.metadata.entry_points()
            
            # Handle both old and new entry_points API
            if hasattr(entry_points, 'select'):
                # Python 3.10+ API
                fastjob_plugins = entry_points.select(group='fastjob.plugins')
            else:
                # Python 3.8-3.9 API
                fastjob_plugins = entry_points.get('fastjob.plugins', [])
            
            for entry_point in fastjob_plugins:
                try:
                    plugin_class = entry_point.load()
                    plugin_instance = plugin_class()
                    plugins[entry_point.name] = plugin_instance
                    logger.info(f"Loaded FastJob plugin: {entry_point.name}")
                except Exception as e:
                    logger.warning(f"Failed to load plugin {entry_point.name}: {e}")
                    
        except Exception as e:
            logger.debug(f"Plugin discovery failed: {e}")
        
        return plugins
    
    def load_plugins(self):
        """Load all discovered plugins."""
        plugins = self.discover_plugins()
        
        for name, plugin in plugins.items():
            try:
                # Initialize the plugin
                if hasattr(plugin, 'initialize'):
                    plugin.initialize()
                
                # Register plugin hooks
                if hasattr(plugin, 'register_hooks'):
                    hooks = plugin.register_hooks()
                    self.hooks.update(hooks)
                
                self.loaded_plugins[name] = plugin
                
            except Exception as e:
                logger.warning(f"Failed to initialize plugin {name}: {e}")
    
    def get_plugin(self, name: str) -> Optional[Any]:
        """Get a loaded plugin by name."""
        return self.loaded_plugins.get(name)
    
    def call_hook(self, hook_name: str, *args, **kwargs):
        """Call all functions registered for a specific hook."""
        hook_functions = self.hooks.get(hook_name, [])
        results = []
        
        for func in hook_functions:
            try:
                result = func(*args, **kwargs)
                results.append(result)
            except Exception as e:
                logger.warning(f"Hook {hook_name} function failed: {e}")
        
        return results
    
    def has_hook(self, hook_name: str) -> bool:
        """Check if a hook has any registered functions."""
        return hook_name in self.hooks and len(self.hooks[hook_name]) > 0


# Global plugin manager instance
_plugin_manager = PluginManager()


def get_plugin_manager() -> PluginManager:
    """Get the global plugin manager instance."""
    return _plugin_manager


def discover_and_load_plugins():
    """Discover and load all FastJob plugins."""
    _plugin_manager.load_plugins()


def get_plugin(name: str) -> Optional[Any]:
    """Get a loaded plugin by name."""
    return _plugin_manager.get_plugin(name)


def call_hook(hook_name: str, *args, **kwargs):
    """Call all functions registered for a specific hook."""
    return _plugin_manager.call_hook(hook_name, *args, **kwargs)


def has_plugin_feature(feature_name: str) -> bool:
    """Check if a plugin feature is available."""
    return _plugin_manager.has_hook(feature_name)


# Base plugin class for plugins to inherit from
class FastJobPlugin:
    """Base class for FastJob plugins."""
    
    def initialize(self):
        """Initialize the plugin. Called when plugin is loaded."""
        pass
    
    def register_hooks(self) -> Dict[str, List[Any]]:
        """Register hooks that this plugin provides.
        
        Returns:
            Dict mapping hook names to lists of callable functions
        """
        return {}
    
    def get_plugin_info(self) -> Dict[str, Any]:
        """Get information about this plugin."""
        return {
            'name': getattr(self, 'name', self.__class__.__name__),
            'version': getattr(self, 'version', '0.1.0'),
            'description': getattr(self, 'description', '')
        }