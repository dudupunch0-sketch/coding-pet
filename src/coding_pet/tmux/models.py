from __future__ import annotations

from dataclasses import dataclass

from coding_pet.models import AgentKind


@dataclass(frozen=True, slots=True)
class TmuxPaneInfo:
    pane_id: str
    session_name: str
    window_pane: str
    current_command: str
    current_path: str
    title: str | None = None


@dataclass(frozen=True, slots=True)
class MatchedTmuxPane:
    pane: TmuxPaneInfo
    agent_kind: AgentKind
    reason: str


@dataclass(frozen=True, slots=True)
class IgnoredTmuxPane:
    pane: TmuxPaneInfo
    reason: str


@dataclass(frozen=True, slots=True)
class TmuxDiscoveryResult:
    matched: list[MatchedTmuxPane]
    ignored: list[IgnoredTmuxPane]
