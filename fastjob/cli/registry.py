"""
CLI Command Registry System for Better Extensibility

Provides a clean command registration system that allows plugins
and core components to register commands dynamically.
"""

from typing import Dict, Callable, Optional, Any, List
import argparse
import logging

logger = logging.getLogger(__name__)


class CLICommand:
    """Represents a single CLI command."""
    
    def __init__(
        self,
        name: str,
        help: str,
        description: str,
        handler: Callable,
        arguments: Optional[List[Dict[str, Any]]] = None,
        aliases: Optional[List[str]] = None,
        category: str = "core"
    ):
        self.name = name
        self.help = help
        self.description = description
        self.handler = handler
        self.arguments = arguments or []
        self.aliases = aliases or []
        self.category = category
    
    def add_to_parser(self, subparsers):
        """Add this command to an argparse subparsers object."""
        # Create the main parser
        parser = subparsers.add_parser(
            self.name,
            help=self.help,
            description=self.description,
            aliases=self.aliases
        )
        
        # Add arguments
        for arg_config in self.arguments:
            args = arg_config.get("args", [])
            kwargs = arg_config.get("kwargs", {})
            parser.add_argument(*args, **kwargs)
        
        # Set the handler
        parser.set_defaults(func=self.handler)
        
        return parser


class CLIRegistry:
    """Registry for CLI commands with categorization and priority."""
    
    def __init__(self):
        self.commands: Dict[str, CLICommand] = {}
        self.categories: Dict[str, List[str]] = {}
    
    def register_command(self, command: CLICommand):
        """Register a command in the registry."""
        if command.name in self.commands:
            logger.warning(f"Command '{command.name}' is already registered. Overriding.")
        
        self.commands[command.name] = command
        
        # Add to category
        if command.category not in self.categories:
            self.categories[command.category] = []
        self.categories[command.category].append(command.name)
        
        logger.debug(f"Registered CLI command: {command.name} (category: {command.category})")
    
    def register_simple_command(
        self,
        name: str,
        help: str,
        handler: Callable,
        description: Optional[str] = None,
        arguments: Optional[List[Dict[str, Any]]] = None,
        aliases: Optional[List[str]] = None,
        category: str = "core"
    ):
        """Helper method to register a command with minimal setup."""
        command = CLICommand(
            name=name,
            help=help,
            description=description or help,
            handler=handler,
            arguments=arguments,
            aliases=aliases,
            category=category
        )
        self.register_command(command)
    
    def get_command(self, name: str) -> Optional[CLICommand]:
        """Get a command by name."""
        return self.commands.get(name)
    
    def get_commands_by_category(self, category: str) -> List[CLICommand]:
        """Get all commands in a specific category."""
        command_names = self.categories.get(category, [])
        return [self.commands[name] for name in command_names if name in self.commands]
    
    def get_all_commands(self) -> List[CLICommand]:
        """Get all registered commands."""
        return list(self.commands.values())
    
    def get_categories(self) -> List[str]:
        """Get all available categories."""
        return list(self.categories.keys())
    
    def add_to_parser(self, subparsers):
        """Add all registered commands to a subparsers object."""
        for command in self.commands.values():
            try:
                command.add_to_parser(subparsers)
            except Exception as e:
                logger.error(f"Failed to add command '{command.name}' to parser: {e}")
    
    def get_registry_status(self) -> Dict[str, Any]:
        """Get status information about the command registry."""
        return {
            "total_commands": len(self.commands),
            "categories": {
                category: len(commands) 
                for category, commands in self.categories.items()
            },
            "command_names": list(self.commands.keys())
        }


# Global command registry
_registry = CLIRegistry()


def get_cli_registry() -> CLIRegistry:
    """Get the global CLI command registry."""
    return _registry


def register_command(command: CLICommand):
    """Register a command in the global registry."""
    _registry.register_command(command)


def register_simple_command(
    name: str,
    help: str,
    handler: Callable,
    description: Optional[str] = None,
    arguments: Optional[List[Dict[str, Any]]] = None,
    aliases: Optional[List[str]] = None,
    category: str = "core"
):
    """Helper to register a simple command in the global registry."""
    _registry.register_simple_command(
        name, help, handler, description, arguments, aliases, category
    )