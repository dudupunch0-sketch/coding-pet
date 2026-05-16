from __future__ import annotations

from fnmatch import fnmatch

from coding_pet.config import TmuxConfig
from coding_pet.models import AgentKind
from coding_pet.tmux.models import (
    IgnoredTmuxPane,
    MatchedTmuxPane,
    TmuxDiscoveryResult,
    TmuxPaneInfo,
)


def parse_list_panes_output(output: str) -> list[TmuxPaneInfo]:
    panes: list[TmuxPaneInfo] = []
    for raw_line in output.splitlines():
        line = raw_line.rstrip("\n")
        if not line.strip():
            continue
        parts = line.split("|", maxsplit=5)
        if len(parts) != 6:
            continue
        pane_id, session_name, window_pane, current_command, current_path, title = parts
        if not pane_id or not session_name:
            continue
        panes.append(
            TmuxPaneInfo(
                pane_id=pane_id,
                session_name=session_name,
                window_pane=window_pane,
                current_command=current_command,
                current_path=current_path,
                title=title or None,
            )
        )
    return panes


def infer_agent_kind(pane: TmuxPaneInfo) -> AgentKind | None:
    haystack = " ".join(
        item.lower()
        for item in (pane.current_command, pane.session_name, pane.title or "")
        if item
    )
    if "opencode" in haystack:
        return AgentKind.OPENCODE
    if "claude" in haystack:
        return AgentKind.CLAUDE_CODE
    return None


def _matches_any(value: str | None, patterns: list[str]) -> bool:
    if not value:
        return False
    return any(fnmatch(value, pattern) for pattern in patterns)


def _is_included(pane: TmuxPaneInfo, config: TmuxConfig) -> bool:
    if pane.current_command in config.include_commands:
        return True
    return _matches_any(pane.session_name, config.include_session_patterns) or _matches_any(
        pane.title,
        config.include_session_patterns,
    )


def discover_agent_panes(
    panes: list[TmuxPaneInfo],
    *,
    config: TmuxConfig,
) -> TmuxDiscoveryResult:
    matched: list[MatchedTmuxPane] = []
    ignored: list[IgnoredTmuxPane] = []
    for pane in panes:
        if _matches_any(pane.session_name, config.exclude_session_patterns):
            ignored.append(IgnoredTmuxPane(pane=pane, reason="excluded by session pattern"))
            continue
        if not _is_included(pane, config):
            ignored.append(IgnoredTmuxPane(pane=pane, reason="no matching agent rule"))
            continue
        agent_kind = infer_agent_kind(pane)
        if agent_kind is None:
            ignored.append(IgnoredTmuxPane(pane=pane, reason="no supported agent kind"))
            continue
        matched.append(MatchedTmuxPane(pane=pane, agent_kind=agent_kind, reason="matched"))
    return TmuxDiscoveryResult(matched=matched, ignored=ignored)
