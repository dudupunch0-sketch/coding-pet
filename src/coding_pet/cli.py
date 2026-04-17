from __future__ import annotations

import asyncio
import uuid

import typer

from coding_pet.daemon.app import DaemonApp
from coding_pet.models import AgentKind

AGENT_OPTION = typer.Option(..., "--agent", case_sensitive=False)
CMD_OPTION = typer.Option(..., "--cmd")
WORKSPACE_OPTION = typer.Option(..., "--workspace")
TITLE_OPTION = typer.Option(None, "--title")
SESSION_ID_OPTION = typer.Option(None, "--session-id")

app = typer.Typer(help="Coding Pet command line interface")
daemon_app = typer.Typer(help="Run and manage the Coding Pet daemon")
widget_app = typer.Typer(help="Run and manage Coding Pet widgets")
admin_app = typer.Typer(help="Administrative and diagnostic commands")

app.add_typer(daemon_app, name="daemon")
app.add_typer(widget_app, name="widget")
app.add_typer(admin_app, name="admin")


@daemon_app.command("run")
def daemon_run() -> None:
    """Run the Coding Pet daemon."""
    typer.echo("Daemon service startup is not implemented yet.")
    raise typer.Exit(code=1)


@daemon_app.command("monitor")
def daemon_monitor(
    agent: AgentKind = AGENT_OPTION,
    cmd: str = CMD_OPTION,
    workspace: str = WORKSPACE_OPTION,
    title: str | None = TITLE_OPTION,
    session_id: str | None = SESSION_ID_OPTION,
) -> None:
    """Launch and monitor a single agent command."""
    resolved_session_id = session_id or f"{agent.value}-{uuid.uuid4().hex[:8]}"
    app_instance = DaemonApp()
    asyncio.run(
        app_instance.monitor_command(
            agent_kind=agent,
            command=cmd,
            workspace=workspace,
            session_id=resolved_session_id,
            title=title,
        )
    )
    typer.echo(f"Monitored session {resolved_session_id}")


@widget_app.command("run")
def widget_run() -> None:
    """Run the Coding Pet widget layer."""
    typer.echo("Widget runtime is not implemented yet.")
    raise typer.Exit(code=1)


@admin_app.command("doctor")
def admin_doctor() -> None:
    """Run basic environment diagnostics."""
    typer.echo("Diagnostics are not implemented yet.")
    raise typer.Exit(code=1)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
