from shellmate.ui.scenes.status import render_status

from shellmate.daemon.lifecycle import check_daemon_status
from shellmate.providers.router import get_provider_status
from shellmate.config.credentials import get_credential_status
from shellmate.config.defaults import get_default_config
from shellmate.ui.runtime.console_factory import ConsoleFactory


def status():
    daemon_status = check_daemon_status()
    provider_status = get_provider_status()
    credential_status = get_credential_status()
    config = get_default_config()

    agent_status = None
    if daemon_status.get("status") == "running":
        # Optional: agents may be absent from lifecycle status
        agent_status = daemon_status.get("agents")

    factory = ConsoleFactory()
    console = factory.create()
    render_status(
        daemon_status,
        provider_status,
        credential_status,
        agent_status=agent_status,
        config=config,
        console=console,
        plain=factory.is_plain(),
    )

    # Surface any non-fatal provider warnings (e.g. an unreachable risk model
    # that would silently fall back to a static rating) on every status call.
    for warning in daemon_status.get("provider_warnings", []) or []:
        message = warning.get("message") if isinstance(warning, dict) else str(warning)
        if message:
            console.print(f"[yellow]WARNING:[/yellow] {message}")
