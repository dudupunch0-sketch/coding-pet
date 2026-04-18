from __future__ import annotations

import asyncio
import os
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path

import typer

from coding_pet.config import load_config
from coding_pet.daemon.app import DaemonApp
from coding_pet.daemon.runtime import DaemonRuntime
from coding_pet.models import AgentKind
from coding_pet.state_store import StateStore

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


async def _serve_daemon_runtime(*, oneshot: bool) -> DaemonRuntime:
    config = load_config()
    runtime = DaemonRuntime(
        runtime_dir=config.runtime_dir,
        state_store=StateStore(config.state_file),
    )
    ready_message = (
        "coding-pet daemon ready "
        f"runtime_dir={config.runtime_dir} "
        f"state_file={config.state_file} "
        f"socket_path={runtime.socket_path}"
    )
    typer.echo(
        ready_message
    )
    await runtime.serve(oneshot=oneshot)
    return runtime


@daemon_app.command("run")
def daemon_run() -> None:
    """Run the Coding Pet daemon."""
    oneshot = os.getenv("CODING_PET_DAEMON_ONESHOT") in {"1", "true", "yes", "on"}
    try:
        asyncio.run(_serve_daemon_runtime(oneshot=oneshot))
    except KeyboardInterrupt:
        typer.echo("coding-pet daemon stopped")


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
    config = load_config()
    typer.echo(
        "coding-pet widget "
        f"runtime_dir={config.runtime_dir} state_file={config.state_file}"
    )
    from coding_pet.gui.app import CodingPetWidgetApp
    from coding_pet.models import AgentKind, AttentionState, SessionStatus

    app = CodingPetWidgetApp()
    demo = SessionStatus(
        session_id="demo",
        agent_kind=AgentKind.CLAUDE_CODE,
        title="Demo Session",
        workspace=str(Path.cwd()),
        state=AttentionState.NEEDS_PERMISSION,
        summary="Waiting for approval to apply changes.",
        last_event_at=datetime.now(UTC),
    )
    try:
        qt_app = app.ensure_app()
    except Exception:
        typer.echo("PySide6 GUI runtime is unavailable in this environment.")
        return
    app.show_sessions([demo])
    raise typer.Exit(code=qt_app.exec())


@admin_app.command("doctor")
def admin_doctor() -> None:
    """Run basic environment diagnostics."""
    config = load_config()
    typer.echo(f"config_dir={config.config_dir}")
    typer.echo(f"state_dir={config.state_dir}")
    typer.echo(f"runtime_dir={config.runtime_dir}")
    typer.echo(f"state_file={config.state_file}")
    typer.echo(f"log_dir={config.log_dir}")
    typer.echo(f"log_level={config.log_level}")
    typer.echo(f"python={shutil.which('python') or shutil.which('python3') or 'unavailable'}")
    typer.echo(f"notify_send={shutil.which('notify-send') or 'unavailable'}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
