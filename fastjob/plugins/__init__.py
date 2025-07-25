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
                    logger.info(f"Successfully loaded FastJob plugin: {entry_point.name} v{getattr(plugin_instance, 'version', '0.1.0')}")
                except Exception as e:
                    logger.error(
                        f"Failed to load plugin '{entry_point.name}': {type(e).__name__}: {e}\n"
                        f"  Plugin entry point: {entry_point}\n"
                        f"  This plugin will be skipped. Check plugin installation and compatibility."
                    )
                    # Store failed plugin info for debugging
                    plugins[f"__failed_{entry_point.name}"] = {
                        "name": entry_point.name,
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "entry_point": str(entry_point)
                    }
                    
        except Exception as e:
            logger.debug(f"Plugin discovery failed: {e}")
        
        return plugins
    
    def load_plugins(self):
        """Load all discovered plugins."""
        plugins = self.discover_plugins()
        
        for name, plugin in plugins.items():
            # Skip failed plugins (they start with __failed_)
            if name.startswith("__failed_"):
                continue
                
            try:
                # Initialize the plugin
                if hasattr(plugin, 'initialize'):
                    plugin.initialize()
                    logger.debug(f"Initialized plugin {name}")
                
                # Register plugin hooks
                if hasattr(plugin, 'register_hooks'):
                    hooks = plugin.register_hooks()
                    if hooks:
                        self.hooks.update(hooks)
                        hook_names = list(hooks.keys())
                        logger.info(f"Plugin {name} registered hooks: {', '.join(hook_names)}")
                    else:
                        logger.debug(f"Plugin {name} registered no hooks")
                
                self.loaded_plugins[name] = plugin
                logger.info(f"Plugin {name} fully loaded and active")
                
            except Exception as e:
                logger.error(
                    f"Failed to initialize plugin '{name}': {type(e).__name__}: {e}\n"
                    f"  Plugin class: {plugin.__class__.__name__}\n"
                    f"  This plugin will be disabled. Check plugin documentation for requirements."
                )
                # Store initialization failure info
                self.loaded_plugins[f"__failed_init_{name}"] = {
                    "name": name,
                    "plugin": plugin,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "stage": "initialization"
                }
    
    def get_plugin(self, name: str) -> Optional[Any]:
        """Get a loaded plugin by name."""
        return self.loaded_plugins.get(name)
    
    def call_hook(self, hook_name: str, *args, **kwargs):
        """Call all functions registered for a specific hook."""
        hook_functions = self.hooks.get(hook_name, [])
        results = []
        errors = []
        
        if not hook_functions:
            logger.debug(f"No functions registered for hook '{hook_name}'")
            return results
        
        logger.debug(f"Calling hook '{hook_name}' with {len(hook_functions)} function(s)")
        
        for i, func in enumerate(hook_functions):
            try:
                result = func(*args, **kwargs)
                results.append(result)
                logger.debug(f"Hook '{hook_name}' function {i+1} executed successfully")
            except Exception as e:
                error_info = {
                    "hook_name": hook_name,
                    "function_index": i,
                    "function": str(func),
                    "error": str(e),
                    "error_type": type(e).__name__
                }
                errors.append(error_info)
                logger.error(
                    f"Hook '{hook_name}' function {i+1} failed: {type(e).__name__}: {e}\n"
                    f"  Function: {func}\n"
                    f"  Args: {args}\n"
                    f"  Kwargs: {kwargs}\n"
                    f"  Continuing with remaining hook functions..."
                )
        
        if errors:
            logger.warning(f"Hook '{hook_name}' completed with {len(errors)} error(s) out of {len(hook_functions)} function(s)")
        
        return results
    
    def has_hook(self, hook_name: str) -> bool:
        """Check if a hook has any registered functions."""
        return hook_name in self.hooks and len(self.hooks[hook_name]) > 0
    
    def get_plugin_status(self) -> Dict[str, Any]:
        """Get comprehensive status of all plugins."""
        active_plugins = {}
        failed_plugins = []
        
        for name, plugin in self.loaded_plugins.items():
            if name.startswith("__failed_"):
                failed_plugins.append(plugin)
            else:
                try:
                    plugin_info = plugin.get_plugin_info() if hasattr(plugin, 'get_plugin_info') else {}
                    active_plugins[name] = {
                        "name": plugin_info.get("name", name),
                        "version": plugin_info.get("version", "unknown"),
                        "description": plugin_info.get("description", "No description"),
                        "class": plugin.__class__.__name__,
                        "hooks_registered": len([h for h, funcs in self.hooks.items() if any(f.__self__ == plugin for f in funcs if hasattr(f, '__self__'))]),
                        "status": "active"
                    }
                except Exception as e:
                    active_plugins[name] = {
                        "name": name,
                        "status": "error_getting_info",
                        "error": str(e)
                    }
        
        return {
            "active_plugins": active_plugins,
            "failed_plugins": failed_plugins,
            "total_hooks": len(self.hooks),
            "hook_names": list(self.hooks.keys()),
            "summary": {
                "active_count": len(active_plugins),
                "failed_count": len(failed_plugins),
                "total_discovered": len(active_plugins) + len(failed_plugins)
            }
        }
    
    def diagnose_plugins(self) -> str:
        """Generate a diagnostic report for plugin troubleshooting."""
        status = self.get_plugin_status()
        
        report = ["=== FastJob Plugin Diagnostic Report ==="]
        
        # Summary
        summary = status["summary"]
        report.append(f"\nSUMMARY:")
        report.append(f"  Active plugins: {summary['active_count']}")
        report.append(f"  Failed plugins: {summary['failed_count']}")
        report.append(f"  Total hooks: {status['total_hooks']}")
        
        # Active plugins
        if status["active_plugins"]:
            report.append(f"\nACTIVE PLUGINS:")
            for name, info in status["active_plugins"].items():
                report.append(f"  ✅ {info['name']} v{info['version']}")
                report.append(f"     Class: {info['class']}")
                report.append(f"     Description: {info['description']}")
                if info.get("hooks_registered", 0) > 0:
                    report.append(f"     Hooks: {info['hooks_registered']} registered")
        
        # Failed plugins
        if status["failed_plugins"]:
            report.append(f"\nFAILED PLUGINS:")
            for failed in status["failed_plugins"]:
                report.append(f"  ❌ {failed['name']}")
                report.append(f"     Error: {failed['error_type']}: {failed['error']}")
                if 'entry_point' in failed:
                    report.append(f"     Entry point: {failed['entry_point']}")
                if failed.get('stage') == 'initialization':
                    report.append(f"     Failed during: Plugin initialization")
                else:
                    report.append(f"     Failed during: Plugin loading")
        
        # Hooks
        if status["hook_names"]:
            report.append(f"\nREGISTERED HOOKS:")
            for hook_name in sorted(status["hook_names"]):
                hook_count = len(self.hooks[hook_name])
                report.append(f"  🔌 {hook_name} ({hook_count} function{'s' if hook_count != 1 else ''})")
        
        return "\n".join(report)


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


def get_plugin_status() -> Dict[str, Any]:
    """Get comprehensive status of all plugins."""
    return _plugin_manager.get_plugin_status()


def diagnose_plugins() -> str:
    """Generate a diagnostic report for plugin troubleshooting."""
    return _plugin_manager.diagnose_plugins()


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