from __future__ import annotations

from coding_pet.config import TmuxConfig
from coding_pet.models import AgentKind
from coding_pet.tmux.discovery import discover_agent_panes, parse_list_panes_output


def test_parse_list_panes_output_handles_valid_rows_and_titles_with_separator() -> None:
    panes = parse_list_panes_output(
        "%3|claude-auth|0.0|claude|/proj/ws/auth|claude-auth\n"
        "%5|opencode-build|1.0|opencode|/proj/ws/build|title|with|pipes\n"
    )

    assert panes[0].pane_id == "%3"
    assert panes[0].session_name == "claude-auth"
    assert panes[0].window_pane == "0.0"
    assert panes[0].current_command == "claude"
    assert panes[0].current_path == "/proj/ws/auth"
    assert panes[0].title == "claude-auth"
    assert panes[1].title == "title|with|pipes"


def test_parse_list_panes_output_ignores_empty_and_malformed_rows() -> None:
    panes = parse_list_panes_output("\nmalformed\n%7|shell|0.0|bash|/tmp|debug\n")

    assert len(panes) == 1
    assert panes[0].pane_id == "%7"


def test_discover_agent_panes_matches_commands_and_patterns_and_excludes() -> None:
    panes = parse_list_panes_output(
        "%3|claude-auth|0.0|claude|/proj/ws/auth|claude-auth\n"
        "%5|opencode-build|0.0|node|/proj/ws/build|opencode-build\n"
        "%6|codex-refactor|0.0|codex|/proj/ws/codex|codex-refactor\n"
        "%7|shell|0.0|bash|/proj/ws/debug|debug\n"
        "%9|claude-ignore|0.0|claude|/proj/ws/ignore|claude-ignore\n"
    )
    config = TmuxConfig(exclude_session_patterns=["*-ignore"])

    discovered = discover_agent_panes(panes, config=config)

    assert [(item.pane.pane_id, item.agent_kind) for item in discovered.matched] == [
        ("%3", AgentKind.CLAUDE_CODE),
        ("%5", AgentKind.OPENCODE),
        ("%6", AgentKind.CODEX),
    ]
    assert {item.pane.pane_id: item.reason for item in discovered.ignored} == {
        "%7": "no matching agent rule",
        "%9": "excluded by session pattern",
    }
