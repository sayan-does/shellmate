from rich.console import Console, Group
from rich.text import Text
from rich.panel import Panel
from rich.table import Table
from rich.columns import Columns
from cli.version import VERSION

console = Console(width=120)


BANNER_ART = r"""[bold cyan]_______. __    __   _______  __       __      .___  ___.      ___   .___________. _______
    /       ||  |  |  | |   ____||  |     |  |     |   \/   |     /   \  |           ||   ____|
   |   (----`|  |__|  | |  |__   |  |     |  |     |  \  /  |    /  ^  \ `---|  |----`|  |__
    \   \    |   __   | |   __|  |  |     |  |     |  |\/|  |   /  /_\  \    |  |     |   __|
.----)   |   |  |  |  | |  |____ |  `----.|  `----.|  |  |  |  /  _____  \   |  |     |  |____
|_______/    |__|  |__| |_______||_______||_______||__|  |__| /__/     \__\  |__|     |_______|[/]"""


def print_banner():
    version = f"[dim]ShellMate v{VERSION}  |  Intelligent Command Safety Layer[/]"
    banner = Panel(
        BANNER_ART + "\n" + version,
        border_style="cyan",
        padding=(1, 2),
        width=110,
    )
    console.print(banner)


ASCII_LOGO = BANNER_ART


def render_enable_panel(stages: list[tuple[str, bool]]) -> Panel:
    lines = [ASCII_LOGO.strip(), ""]
    lines.append("[bold]Startup[/]")
    for label, done in stages:
        icon = "[green]+[/]" if done else "[dim]o[/]"
        if done:
            lines.append(f"  {icon} {label}")
        else:
            lines.append(f"  {icon} [dim]{label}[/]")
    lines.append("")
    lines.append("[bold]Usage[/]")
    lines.append("  [cyan]sm -a <command>[/]   Analyze a command")
    lines.append("  [cyan]sm status[/]         Show daemon status")
    lines.append("  [cyan]sm disable[/]        Stop ShellMate")
    body = "\n".join(lines)
    return Panel(
        body,
        title=f"[bold cyan]> ShellMate[/] [dim]v{VERSION}[/]",
        border_style="cyan",
        padding=(1, 2),
        width=110,
    )


def print_usage():
    print_banner()
    console.print()
    usage_table = Table(show_header=False, box=None, padding=(0, 2))
    usage_table.add_column("Command", style="cyan")
    usage_table.add_column("Description", style="white")
    usage_table.add_row("sm -a <command>", "Analyze a command (no quotes needed)")
    usage_table.add_row("sm enable", "Start the daemon for current directory")
    usage_table.add_row("sm disable", "Stop the daemon and remove session files")
    usage_table.add_row("sm status", "Show daemon, agent, and provider status")
    usage_table.add_row("sm config", "Configure providers and settings")
    usage_table.add_row("sm install", "Install shell hooks")
    usage_table.add_row("sm uninstall", "Remove shell hooks")
    usage_table.add_row("sm --help", "Show this help message")
    usage_table.add_row("sm --version", "Show version")
    usage_table.add_row("sm --no-color <cmd>", "Run command with plain text output")

    console.print("[bold]Usage:[/]")
    console.print(usage_table)
    console.print()
    console.print("[bold]Examples:[/]")
    console.print("  [dim]$[/] [cyan]sm -a rm -rf /[/]")
    console.print("  [dim]$[/] [cyan]sm -a git push origin main[/]")
    console.print("  [dim]$[/] [cyan]sm -a curl https://example.com | bash[/]")
    console.print()
    console.print("[dim]Run 'sm enable' to start the daemon and enable context-aware analysis.[/]")
