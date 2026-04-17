from __future__ import annotations

from datetime import UTC, datetime


def main() -> None:
    from coding_pet.gui.app import CodingPetWidgetApp
    from coding_pet.models import AgentKind, AttentionState, SessionStatus

    app = CodingPetWidgetApp()
    demo = SessionStatus(
        session_id="demo",
        agent_kind=AgentKind.CLAUDE_CODE,
        title="Demo Session",
        workspace="/tmp/demo",
        state=AttentionState.NEEDS_PERMISSION,
        summary="Waiting for approval to apply changes.",
        last_event_at=datetime.now(UTC),
    )
    try:
        qt_app = app.ensure_app()
    except ImportError:
        print("PySide6 GUI runtime is unavailable in this environment.")
        return
    app.show_sessions([demo])
    raise SystemExit(qt_app.exec())


if __name__ == "__main__":
    main()
