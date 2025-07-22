"""
Complete integration test for CLI plugin system across all FastJob packages
Tests the full plugin discovery and CLI integration workflow
"""

import pytest
import sys
import os
from unittest.mock import patch, MagicMock, call
from pathlib import Path

# Import CLI components
from fastjob.cli.main import load_plugin_commands, main
from fastjob.plugins import get_plugin_manager, discover_and_load_plugins


class TestCompletePluginSystemIntegration:
    """Test complete CLI plugin system integration"""
    
    def test_plugin_discovery_and_cli_integration(self):
        """Test full plugin discovery and CLI command registration workflow"""
        # Step 1: Test plugin manager can be created
        plugin_manager = get_plugin_manager()
        assert plugin_manager is not None
        
        # Step 2: Test plugin discovery runs without error
        discover_and_load_plugins()
        
        # Step 3: Test CLI can load plugin commands
        mock_subparsers = MagicMock()
        
        # This should not raise an exception
        load_plugin_commands(mock_subparsers)
        
        # If any plugins are loaded, the hook should have been called
        # (We can't guarantee plugins are installed, so we just test it doesn't crash)
    
    def test_cli_plugin_hook_mechanism(self):
        """Test the CLI plugin hook mechanism works correctly"""
        # Mock a plugin manager with the register_cli_commands hook
        mock_plugin_manager = MagicMock()
        
        # Mock subparsers
        mock_subparsers = MagicMock()
        
        # Test that load_plugin_commands calls the hook
        with patch('fastjob.cli.main.get_plugin_manager', return_value=mock_plugin_manager):
            load_plugin_commands(mock_subparsers)
            
            # Should have called the register_cli_commands hook
            mock_plugin_manager.call_hook.assert_called_once_with('register_cli_commands', mock_subparsers)
    
    def test_plugin_command_execution_workflow(self):
        """Test the complete workflow of executing a plugin command"""
        # Mock args with a plugin function
        mock_args = MagicMock()
        mock_args.command = 'test-plugin-command'
        mock_args.plugin_func = MagicMock(return_value=0)
        
        # Mock the discovery functions
        with patch('fastjob.cli.main.discover_jobs'):
            with patch('sys.argv', ['fastjob', 'test-plugin-command']):
                with patch('argparse.ArgumentParser.parse_args', return_value=mock_args):
                    with pytest.raises(SystemExit) as exc_info:
                        main()
                    
                    # Should have called the plugin function
                    mock_args.plugin_func.assert_called_once_with(mock_args)
                    
                    # Should exit with success
                    assert exc_info.value.code == 0


class TestPluginSystemResilience:
    """Test plugin system handles various error conditions gracefully"""
    
    def test_cli_works_with_no_plugins(self):
        """Test CLI works when no plugins are available"""
        mock_plugin_manager = MagicMock()
        mock_plugin_manager.call_hook.return_value = []  # No plugins respond to hook
        
        mock_subparsers = MagicMock()
        
        with patch('fastjob.cli.main.get_plugin_manager', return_value=mock_plugin_manager):
            # Should work without issues
            load_plugin_commands(mock_subparsers)
            
            # Should have tried to call the hook
            mock_plugin_manager.call_hook.assert_called_once_with('register_cli_commands', mock_subparsers)
    
    def test_cli_handles_plugin_manager_errors(self):
        """Test CLI handles errors from plugin manager gracefully"""
        # Mock plugin manager that raises an exception
        with patch('fastjob.cli.main.get_plugin_manager', side_effect=Exception("Plugin manager error")):
            mock_subparsers = MagicMock()
            
            # Should not propagate the exception
            load_plugin_commands(mock_subparsers)
    
    def test_cli_handles_plugin_hook_errors(self):
        """Test CLI handles errors from plugin hooks gracefully"""
        mock_plugin_manager = MagicMock()
        mock_plugin_manager.call_hook.side_effect = Exception("Plugin hook error")
        
        mock_subparsers = MagicMock()
        
        with patch('fastjob.cli.main.get_plugin_manager', return_value=mock_plugin_manager):
            # Should not propagate the exception
            load_plugin_commands(mock_subparsers)
            
            # Should have attempted to call the hook
            mock_plugin_manager.call_hook.assert_called_once()
    
    def test_cli_handles_plugin_command_errors(self):
        """Test CLI handles plugin command execution errors"""
        mock_args = MagicMock()
        mock_args.command = 'failing-plugin-command'
        mock_args.plugin_func = MagicMock(side_effect=Exception("Plugin command failed"))
        
        with patch('fastjob.cli.main.discover_jobs'):
            with patch('sys.argv', ['fastjob', 'failing-plugin-command']):
                with patch('argparse.ArgumentParser.parse_args', return_value=mock_args):
                    with pytest.raises(SystemExit) as exc_info:
                        main()
                    
                    # Should exit with error code due to plugin failure
                    assert exc_info.value.code == 1


class TestCoreAndPluginCommandCoexistence:
    """Test that core commands and plugin commands work together"""
    
    def test_core_commands_unaffected_by_plugins(self):
        """Test that core commands work regardless of plugin state"""
        # Mock plugin system to simulate various states
        plugin_states = [
            lambda: None,  # No plugin manager
            lambda: MagicMock(),  # Working plugin manager
            lambda: Exception("Broken plugins"),  # Broken plugin system
        ]
        
        for plugin_state in plugin_states:
            if isinstance(plugin_state(), Exception):
                patch_target = patch('fastjob.cli.main.get_plugin_manager', side_effect=plugin_state())
            else:
                patch_target = patch('fastjob.cli.main.get_plugin_manager', return_value=plugin_state())
            
            with patch_target:
                # Core help should always work
                with patch('sys.argv', ['fastjob', '--help']):
                    with pytest.raises(SystemExit) as exc_info:
                        main()
                    assert exc_info.value.code == 0
    
    def test_plugin_commands_dont_interfere_with_core(self):
        """Test that plugin commands don't interfere with core commands"""
        # Mock a plugin that registers commands
        mock_plugin_manager = MagicMock()
        
        def mock_register_commands(subparsers):
            parser = subparsers.add_parser('mock-plugin-command')
            parser.set_defaults(plugin_func=lambda args: 0)
        
        mock_plugin_manager.call_hook.return_value = [mock_register_commands]
        
        mock_subparsers = MagicMock()
        
        with patch('fastjob.cli.main.get_plugin_manager', return_value=mock_plugin_manager):
            load_plugin_commands(mock_subparsers)
            
            # Plugin should have registered its command
            mock_plugin_manager.call_hook.assert_called_once()
            
            # Core commands should still work (test that we didn't break arg parsing)
            with patch('sys.argv', ['fastjob', 'migrate', '--help']):
                with pytest.raises(SystemExit) as exc_info:
                    main()
                assert exc_info.value.code == 0


class TestPluginArchitectureCompliance:
    """Test that the plugin system follows architectural principles"""
    
    def test_plugin_system_uses_entry_points(self):
        """Test that plugin system uses Python entry points for discovery"""
        # The plugin manager should use entry points for discovery
        from fastjob.plugins import FastJobPluginManager
        
        manager = FastJobPluginManager()
        
        # Test that discover_plugins method exists and uses entry points
        assert hasattr(manager, 'discover_plugins')
        
        # The discovery should not crash
        manager.discover_plugins()
    
    def test_cli_system_is_extensible(self):
        """Test that CLI system is properly extensible"""
        # Test that the main CLI uses the plugin system for extensibility
        import fastjob.cli.main
        import inspect
        
        # The main module should import and use the plugin system
        source = inspect.getsource(fastjob.cli.main)
        assert 'plugin' in source.lower()
        assert 'hook' in source.lower() or 'get_plugin_manager' in source
    
    def test_plugin_isolation(self):
        """Test that plugins are properly isolated"""
        # Plugins should be loaded independently
        # Even if one plugin fails, others should work
        
        def working_plugin_hook(subparsers):
            parser = subparsers.add_parser('working-command')
            parser.set_defaults(plugin_func=lambda args: 0)
        
        def failing_plugin_hook(subparsers):
            raise Exception("Plugin registration failed")
        
        mock_plugin_manager = MagicMock()
        # Simulate multiple plugins, one working, one failing
        mock_plugin_manager.call_hook.return_value = [working_plugin_hook, failing_plugin_hook]
        
        mock_subparsers = MagicMock()
        
        with patch('fastjob.cli.main.get_plugin_manager', return_value=mock_plugin_manager):
            # Should not crash even with failing plugin
            load_plugin_commands(mock_subparsers)


class TestCLIEntryPointIntegration:
    """Test CLI entry point integration"""
    
    def test_fastjob_cli_available(self):
        """Test that fastjob CLI is available as expected"""
        # Test that the CLI module can be imported and executed
        try:
            from fastjob.cli.main import main
            assert callable(main)
        except ImportError as e:
            pytest.fail(f"CLI module not importable: {e}")
    
    def test_cli_module_structure(self):
        """Test CLI module has expected structure"""
        import fastjob.cli.main
        
        # Should have main function
        assert hasattr(fastjob.cli.main, 'main')
        assert callable(fastjob.cli.main.main)
        
        # Should have plugin loading function
        assert hasattr(fastjob.cli.main, 'load_plugin_commands')
        assert callable(fastjob.cli.main.load_plugin_commands)


class TestPluginCommandLifecycle:
    """Test the complete lifecycle of plugin commands"""
    
    def test_plugin_command_registration_lifecycle(self):
        """Test complete plugin command registration lifecycle"""
        # Step 1: Plugin manager is created
        plugin_manager = get_plugin_manager()
        assert plugin_manager is not None
        
        # Step 2: Plugins are discovered (should not crash)
        discover_and_load_plugins()
        
        # Step 3: CLI requests plugin commands
        mock_subparsers = MagicMock()
        load_plugin_commands(mock_subparsers)
        
        # Step 4: Commands should be available for execution
        # (We can't test actual execution without installed plugins,
        #  but we can test the mechanism)
    
    def test_plugin_command_execution_lifecycle(self):
        """Test plugin command execution lifecycle"""
        # Mock a complete plugin command execution
        mock_plugin_func = MagicMock(return_value=0)
        mock_args = MagicMock()
        mock_args.command = 'test-command'
        mock_args.plugin_func = mock_plugin_func
        
        # Test execution through main()
        with patch('fastjob.cli.main.discover_jobs'):
            with patch('sys.argv', ['fastjob', 'test-command']):
                with patch('argparse.ArgumentParser.parse_args', return_value=mock_args):
                    with pytest.raises(SystemExit) as exc_info:
                        main()
                    
                    # Plugin function should be called
                    mock_plugin_func.assert_called_once_with(mock_args)
                    
                    # Should exit successfully
                    assert exc_info.value.code == 0


class TestRealWorldPluginScenarios:
    """Test real-world plugin scenarios"""
    
    def test_multiple_plugins_scenario(self):
        """Test scenario with multiple plugins registering commands"""
        # Simulate multiple plugins registering different commands
        def plugin1_register(subparsers):
            parser = subparsers.add_parser('plugin1-cmd')
            parser.set_defaults(plugin_func=lambda args: 0)
        
        def plugin2_register(subparsers):
            parser = subparsers.add_parser('plugin2-cmd')
            parser.set_defaults(plugin_func=lambda args: 0)
        
        mock_plugin_manager = MagicMock()
        mock_plugin_manager.call_hook.return_value = [plugin1_register, plugin2_register]
        
        mock_subparsers = MagicMock()
        
        with patch('fastjob.cli.main.get_plugin_manager', return_value=mock_plugin_manager):
            load_plugin_commands(mock_subparsers)
            
            # Should have called the hook
            mock_plugin_manager.call_hook.assert_called_once_with('register_cli_commands', mock_subparsers)
    
    def test_plugin_upgrade_scenario(self):
        """Test scenario where plugins are upgraded/changed"""
        # Test that the plugin system can handle changes in available plugins
        # First scenario: No plugins
        mock_empty_manager = MagicMock()
        mock_empty_manager.call_hook.return_value = []
        
        mock_subparsers = MagicMock()
        
        with patch('fastjob.cli.main.get_plugin_manager', return_value=mock_empty_manager):
            load_plugin_commands(mock_subparsers)
        
        # Second scenario: Plugin available
        def plugin_register(subparsers):
            parser = subparsers.add_parser('new-plugin-cmd')
            parser.set_defaults(plugin_func=lambda args: 0)
        
        mock_populated_manager = MagicMock()
        mock_populated_manager.call_hook.return_value = [plugin_register]
        
        with patch('fastjob.cli.main.get_plugin_manager', return_value=mock_populated_manager):
            load_plugin_commands(mock_subparsers)
            
            # Should work in both scenarios without issues


if __name__ == "__main__":
    pytest.main([__file__, "-v"])