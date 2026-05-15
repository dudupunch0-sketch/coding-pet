from __future__ import annotations

from dataclasses import dataclass

from coding_pet.models import AgentKind, SessionStatus
from coding_pet.transcripts.model import TranscriptEvent


@dataclass(frozen=True, slots=True)
class TranscriptRowViewModel:
    timestamp: str
    direction: str
    source: str
    text: str


@dataclass(frozen=True, slots=True)
class DetailViewModel:
    session_id: str
    title: str
    state: str
    target_label: str
    cwd: str
    tmux_target: str
    last_activity: str
    last_input: str
    agent_request: str
    transcript_rows: list[TranscriptRowViewModel]


def _agent_label(agent_kind: AgentKind | str) -> str:
    value = agent_kind.value if hasattr(agent_kind, "value") else str(agent_kind)
    return {
        "claude_code": "Claude Code",
        "opencode": "OpenCode",
    }.get(value, value)


def _tmux_label(status: SessionStatus) -> str:
    if status.tmux_session_name and status.tmux_pane_id:
        return f"{status.tmux_session_name}:{status.tmux_pane_id}"
    return status.tmux_pane_id or status.tmux_session_name or "not attached"


def build_detail_view_model(
    status: SessionStatus,
    events: list[TranscriptEvent] | tuple[TranscriptEvent, ...],
) -> DetailViewModel:
    tmux_target = _tmux_label(status)
    cwd = status.workspace
    rows = [
        TranscriptRowViewModel(
            timestamp=event.ts.strftime("%H:%M:%S"),
            direction=event.direction,
            source=event.source,
            text=event.text,
        )
        for event in events
    ]
    return DetailViewModel(
        session_id=status.session_id,
        title=status.title,
        state=status.state.value,
        target_label=f"{_agent_label(status.agent_kind)} · {tmux_target} · {cwd}",
        cwd=cwd,
        tmux_target=tmux_target,
        last_activity=(status.last_activity_at or status.last_event_at).strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
        last_input=status.last_dashboard_input or "",
        agent_request=status.agent_waiting_message or status.estimated_current_request or "",
        transcript_rows=rows,
    )
