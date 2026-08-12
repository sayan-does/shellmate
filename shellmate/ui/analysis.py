from rich.console import Console, Group
from rich.table import Table
from rich.text import Text
from rich.panel import Panel
from rich.columns import Columns
from rich.rule import Rule

console = Console(width=120)

RISK_STYLES = {
    "SAFE": ("green", "[OK]", "bold green", "green"),
    "LOW": ("blue", "[i]", "bold blue", "blue"),
    "MEDIUM": ("yellow", "[!]", "bold yellow", "yellow"),
    "HIGH": ("red", "[!!]", "bold red", "red"),
    "CRITICAL": ("bold red", "[!!!]", "bold white on red", "red"),
}

SEVERITY_ORDER = {"SAFE": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}


def _confidence_bar(confidence: float) -> str:
    bar_len = 12
    filled = int(confidence * bar_len)
    bar = "█" * filled + "░" * (bar_len - filled)
    color = "green" if confidence >= 0.8 else "yellow" if confidence >= 0.5 else "red"
    return f"[{color}]{bar}[/{color}]"


def _latency_table(latency: dict) -> Table:
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Stage", style="dim")
    table.add_column("Time", justify="right")
    for stage, ms in sorted(latency.items(), key=lambda x: -x[1]):
        ms_str = f"{ms:.0f}ms" if ms > 0 else "<1ms"
        table.add_row(f"  {stage}", ms_str)
    return table


def render_analysis(result: dict):
    risk = result.get("risk", "UNKNOWN").upper()
    confidence = result.get("confidence", 0.0)
    message = result.get("message", "") or result.get("explanation", "")
    alternatives = result.get("alternatives", [])
    context_used = result.get("context_used", {})
    latency = result.get("latency", {})
    total_ms = result.get("total_ms", 0)
    early_exit = result.get("early_exit")
    cached = result.get("cached", False)
    warning = result.get("supervisor_warning")
    guide = result.get("command_guide")

    color, prefix, risk_style, border = RISK_STYLES.get(risk, ("white", "[?]", "white", "white"))

    risk_header = Text()
    risk_header.append(f"{prefix} {risk}", style=risk_style)
    if cached:
        risk_header.append("  (cached)", style="dim italic")

    elements = [risk_header]

    if confidence > 0:
        bar = _confidence_bar(confidence)
        elements.append(Text.assemble(" ", bar, f"  {confidence:.0%}", style="dim"))

    if message:
        max_len = 500
        truncated = message[:max_len] + "..." if len(message) > max_len else message
        msg = Text(truncated)
        msg.stylize("white")
        if len(truncated) > 100:
            elements.append(Panel(msg, border_style=border, padding=(0, 1)))
        else:
            elements.append(Text(f"  {truncated}"))

    failed_cred = result.get("failed_credential")
    failed_prov = result.get("failed_provider")
    if failed_cred or failed_prov:
        which = failed_cred or (f"{failed_prov}_API_KEY".upper() if failed_prov else "API key")
        elements.append(
            Text(f"  Failed credential: {which}", style="bold yellow")
        )

    if early_exit:
        exit_msgs = {
            "sanitizer": "Corrected by typo sanitizer",
            "rule_engine": "Matched deterministic rule",
            "cache": "Returned from cache",
        }
        exit_label = exit_msgs.get(early_exit, early_exit)
        elements.append(Text(f"  [dim]Early exit:[/] [italic]{exit_label}[/]"))

    if warning:
        warning_panel = Panel(
            Text(f"! {warning}", style="yellow"),
            border_style="yellow",
            padding=(0, 1),
        )
        elements.append(warning_panel)

    if alternatives:
        alt_label = "Suggestions:" if risk in ("SAFE", "LOW") else "Safer alternatives:"
        alt_parts = [Text(alt_label, style="bold")]
        for i, alt in enumerate(alternatives[:5], 1):
            alt_parts.append(Text(f"  {i}. {alt}"))
        elements.append(Group(*alt_parts))

    if context_used:
        ctx_parts = []
        if context_used.get("watcher"):
            ctx_parts.append("watcher")
        if context_used.get("librarian"):
            ctx_parts.append("librarian")
        if ctx_parts:
            ct = Text(f"   Context: {', '.join(ctx_parts)}")
            ct.stylize("dim italic")
            elements.append(ct)

    if guide:
        guide_parts = []
        if guide.get("intent_guess"):
            guide_parts.append(Text(guide["intent_guess"], style="italic"))
        if guide.get("when_to_use"):
            guide_parts.append(Text(f"  When to use: {guide['when_to_use']}"))
        if guide.get("parameters"):
            guide_parts.append(Text("  Parameters:", style="bold dim"))
            for p in guide.get("parameters") or []:
                guide_parts.append(Text(f"    • {p}"))
        suggested = guide.get("suggested_command") or guide.get("example_command")
        if suggested:
            guide_parts.append(Text.assemble(
                "  Use: ", (suggested, "bold cyan"),
            ))
        if guide_parts:
            guide_panel = Panel(
                Group(*guide_parts),
                border_style="cyan",
                padding=(0, 1),
                title="[bold cyan]Command guide[/bold cyan]",
            )
            elements.append(guide_panel)

    if latency:
        elements.append(Text("Latency breakdown:", style="bold dim"))
        elements.append(_latency_table(latency))

    if total_ms:
        elements.append(Text(f"  Total: {total_ms:.0f}ms", style="dim"))

    main_panel = Panel(
        Group(*elements),
        border_style=border,
        padding=(1, 2),
        title=f"[{color}]{risk} Analysis[/{color}]",
        title_align="left",
    )
    console.print(main_panel)

    suggested_cmd = guide and (guide.get("suggested_command") or guide.get("example_command"))
    if suggested_cmd:
        tip = Text.assemble(
            ("> Tip: ", "bold yellow"),
            (f"Try `{suggested_cmd}` for this operation", "white"),
        )
        console.print(tip)
