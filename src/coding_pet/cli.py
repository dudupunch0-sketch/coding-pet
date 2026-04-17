from __future__ import annotations

import typer

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
    typer.echo("Daemon runtime is not implemented yet.")
    raise typer.Exit(code=1)


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
