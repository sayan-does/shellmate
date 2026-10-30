"""CLI commands for ShellMate"""
from shellmate.cli.commands.enable import enable as enable_command
from shellmate.cli.commands.disable import disable as disable_command
from shellmate.cli.commands.status import status as status_command
from shellmate.cli.commands.config import config as config_command
from shellmate.cli.commands.install import install
from shellmate.cli.commands.uninstall import uninstall

# Do not bind `init` / `migrate` / `enable` on this package — that shadows the
# submodules and breaks `import cli.commands.enable`. Import under aliases.
from shellmate.cli.commands.init import init as init_command
from shellmate.cli.commands.migrate import migrate as migrate_command

__all__ = [
    "enable_command",
    "disable_command",
    "status_command",
    "config_command",
    "install",
    "uninstall",
    "init_command",
    "migrate_command",
]
