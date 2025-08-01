"""
Comprehensive tests for CLI plugin system across all FastJob packages
"""

import pytest
import subprocess
from unittest.mock import patch, MagicMock

# Import the CLI components
from fastjob.cli.main import load_plugin_commands, main
from fastjob.plugins import get_plugin_manager, discover_and_load_plugins


class TestCLIPluginDiscovery:
    """Test CLI plugin discovery mechanism"""

    def test_load_plugin_commands_basic(self):
        """Test that load_plugin_commands doesn't crash"""
        # Should not raise an exception
        load_plugin_commands()

        # The function should have attempted to get the plugin manager
        # (We can't verify much more without actually installing plugins)

    def test_plugin_manager_integration(self):
        """Test that CLI integrates with the plugin manager"""
        plugin_manager = get_plugin_manager()
        assert plugin_manager is not None

        # Test that the plugin manager has hooks attribute
        assert hasattr(plugin_manager, "hooks")
        assert isinstance(plugin_manager.hooks, dict)

    def test_plugin_discovery_runs_without_error(self):
        """Test that plugin discovery completes successfully"""
        # This should not raise an exception
        discover_and_load_plugins()

        # Get the plugin manager and verify it's working
        plugin_manager = get_plugin_manager()
        plugins = plugin_manager.loaded_plugins

        # Should have at least 0 plugins (could be more if Pro/Enterprise are installed)
        assert isinstance(plugins, dict)


class TestCLIBasicCommands:
    """Test basic CLI commands work"""

    def test_cli_main_help(self):
        """Test CLI main help command"""
        # Mock sys.argv to simulate --help
        with patch("sys.argv", ["fastjob", "--help"]):
            # Should not crash and should exit with code 0
            with pytest.raises(SystemExit) as exc_info:
                main()
            # Help command should exit with 0
            assert exc_info.value.code == 0

    def test_cli_main_no_command(self):
        """Test CLI with no command specified"""
        with patch("sys.argv", ["fastjob"]):
            # Should show help and return without crashing
            main()  # Should complete without exception

    def test_cli_unknown_command(self):
        """Test CLI with unknown command"""
        with patch("sys.argv", ["fastjob", "unknown-command"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            # Unknown command should exit with argparse error code (2)
            assert exc_info.value.code == 2


class TestCLIPluginIntegration:
    """Test CLI plugin integration functionality"""

    def test_plugin_command_registration_mechanism(self):
        """Test the mechanism for registering plugin commands"""
        # Create a mock plugin that registers a command
        mock_plugin = MagicMock()

        def mock_register_cli_commands(subparsers):
            # Mock registering a command
            parser = subparsers.add_parser("mock-command", help="Mock command")
            parser.set_defaults(plugin_func=lambda args: 0)

        mock_plugin.register_cli_commands = mock_register_cli_commands

        # Create a mock plugin manager
        mock_plugin_manager = MagicMock()
        mock_plugin_manager.call_hook.return_value = [None]  # Simulate hook call

        with patch(
            "fastjob.plugins.get_plugin_manager", return_value=mock_plugin_manager
        ):
            load_plugin_commands()

            # Verify the hook was called
            mock_plugin_manager.call_hook.assert_called_once_with(
                "register_cli_commands"
            )

    def test_plugin_command_execution_mechanism(self):
        """Test that plugin commands can be executed through the CLI"""
        # Mock an args object with a plugin function
        mock_args = MagicMock()
        mock_args.command = "plugin-command"
        mock_args.func = MagicMock(return_value=0)

        # Mock sys.argv and argparse to return our mock args
        with patch("sys.argv", ["fastjob", "plugin-command"]):
            with patch("argparse.ArgumentParser.parse_args", return_value=mock_args):
                result = main()

                # Should have called the plugin function
                mock_args.func.assert_called_once_with(mock_args)
                # Should return success
                assert result == 0


class TestSpecificCLICommands:
    """Test specific CLI commands"""

    def test_core_commands_available(self):
        """Test that core commands are available"""
        from fastjob.cli.main import main

        # Test that simplified core commands don't crash during argument parsing
        core_commands = ["start", "setup", "status"]

        for command in core_commands:
            with patch("sys.argv", ["fastjob", command, "--help"]):
                with pytest.raises(SystemExit) as exc_info:
                    main()
                # Help should exit with 0
                assert exc_info.value.code == 0

    def test_jobs_subcommands(self):
        """Test jobs functionality integrated into status command"""
        # Jobs functionality is now integrated into the status command with --jobs flag
        with patch("sys.argv", ["fastjob", "status", "--jobs", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

    def test_queues_subcommands(self):
        """Test queues functionality integrated into status command"""
        # Queues functionality is now integrated into the status command with --verbose flag
        with patch("sys.argv", ["fastjob", "status", "--verbose", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0


class TestCLIPluginSystemResilience:
    """Test CLI plugin system handles errors gracefully"""

    def test_plugin_discovery_with_broken_plugin(self):
        """Test CLI works even if a plugin is broken"""

        # Mock a plugin that raises an exception during loading
        def broken_plugin_hook(*args, **kwargs):
            raise Exception("Broken plugin")

        mock_plugin_manager = MagicMock()
        mock_plugin_manager.call_hook.side_effect = Exception("Plugin error")

        with patch(
            "fastjob.plugins.get_plugin_manager", return_value=mock_plugin_manager
        ):
            # Should not raise an exception
            load_plugin_commands()

    def test_cli_works_without_plugins(self):
        """Test CLI works when no plugins are available"""
        # Mock plugin manager to return no plugins
        mock_plugin_manager = MagicMock()
        mock_plugin_manager.call_hook.return_value = []

        with patch(
            "fastjob.plugins.get_plugin_manager", return_value=mock_plugin_manager
        ):
            # Should work fine
            load_plugin_commands()
            mock_plugin_manager.call_hook.assert_called_once()

    def test_plugin_command_failure_handling(self):
        """Test handling of plugin command failures"""
        # Mock args with a failing plugin function
        mock_args = MagicMock()
        mock_args.command = "failing-plugin-command"
        mock_args.func = MagicMock(side_effect=Exception("Plugin command failed"))

        with patch("sys.argv", ["fastjob", "failing-plugin-command"]):
            with patch("argparse.ArgumentParser.parse_args", return_value=mock_args):
                result = main()

                # Should have called the plugin function
                mock_args.func.assert_called_once_with(mock_args)
                # Should return error code
                assert result == 1


class TestCLIEntryPoint:
    """Test CLI entry point configuration"""

    def test_fastjob_command_available(self):
        """Test that fastjob command is available as entry point"""
        # This tests that the setup in pyproject.toml works
        try:
            result = subprocess.run(
                ["python3", "-c", "import fastjob.cli.main; fastjob.cli.main.main"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            # Should not crash (may exit with error due to no args, but should not crash)
            assert result.returncode in [
                0,
                1,
            ]  # 0 for success, 1 for no command specified
        except subprocess.TimeoutExpired:
            pytest.fail("CLI entry point took too long to load")
        except Exception as e:
            pytest.fail(f"CLI entry point failed to load: {e}")


class TestCLIEnvironmentIntegration:
    """Test CLI integrates properly with FastJob environment"""

    def test_cli_loads_fastjob_properly(self):
        """Test that CLI properly loads the FastJob environment"""
        with patch("sys.argv", ["fastjob", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

            # Help should exit with code 0
            assert exc_info.value.code == 0

    def test_cli_plugin_discovery_integration(self):
        """Test that CLI integrates with FastJob's plugin discovery"""
        # Verify that when CLI loads, it attempts to discover plugins
        with patch("fastjob.plugins.get_plugin_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_get_manager.return_value = mock_manager

            load_plugin_commands()

            # Should have tried to get the plugin manager
            mock_get_manager.assert_called_once()
            # Should have called the hook
            mock_manager.call_hook.assert_called_once_with("register_cli_commands")


class TestCLIColorSystem:
    """Test CLI color and status system"""

    def test_color_module_import(self):
        """Test that CLI color module can be imported"""
        from fastjob.cli.colors import print_header, print_status, StatusIcon

        # Should be able to import and use
        assert callable(print_header)
        assert callable(print_status)
        assert hasattr(StatusIcon, "rocket")

    def test_status_functions_work(self):
        """Test that status functions work without crashing"""
        from fastjob.cli.colors import print_status, StatusIcon

        # Should not crash
        print_status("Test message", "info")
        print_status("Test warning", "warning")
        print_status("Test error", "error")
        print_status("Test success", "success")

        # Icons should be callable
        assert callable(StatusIcon.rocket)
        assert callable(StatusIcon.info)


class TestCLIArchitectureCompliance:
    """Test CLI follows FastJob architecture principles"""

    def test_cli_follows_plugin_architecture(self):
        """Test that CLI follows the plugin architecture"""
        # CLI should use the plugin manager for extensibility
        plugin_manager = get_plugin_manager()
        assert plugin_manager is not None

        # Should have the hooks attribute available
        hooks = plugin_manager.hooks
        # Hook might not be registered if no plugins are loaded, so just test manager works
        assert isinstance(hooks, dict)

    def test_cli_does_not_hardcode_plugin_commands(self):
        """Test that CLI doesn't hardcode plugin-specific commands"""
        # The main CLI file should not directly import Pro/Enterprise modules
        from fastjob.cli import main
        import inspect

        source = inspect.getsource(main)

        # Should not directly import Pro/Enterprise modules
        assert "fastjob_pro" not in source
        assert "fastjob_enterprise" not in source

        # Should use plugin system instead
        assert "plugin" in source.lower() or "hook" in source.lower()

    def test_cli_plugin_loading_is_graceful(self):
        """Test that CLI plugin loading is graceful and doesn't break core functionality"""
        # Even if plugin loading fails, core commands should work
        with patch(
            "fastjob.plugins.get_plugin_manager",
            side_effect=Exception("Plugin system broken"),
        ):

            # Should not raise an exception
            load_plugin_commands()

            # Core functionality should still work
            with patch("sys.argv", ["fastjob", "--help"]):
                with pytest.raises(SystemExit) as exc_info:
                    main()
                # Should still exit successfully
                assert exc_info.value.code == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
