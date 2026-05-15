from __future__ import annotations

from coding_pet.tmux.capture import new_output_from_snapshot, snapshot_hash


def test_snapshot_hash_changes_with_text() -> None:
    assert snapshot_hash("a") != snapshot_hash("b")


def test_new_output_from_snapshot_returns_appended_lines() -> None:
    previous = "line 1\nline 2"
    current = "line 1\nline 2\nline 3\nline 4"

    assert new_output_from_snapshot(previous, current) == "line 3\nline 4"


def test_new_output_from_snapshot_returns_empty_for_unchanged_text() -> None:
    assert new_output_from_snapshot("same", "same") == ""


def test_new_output_from_snapshot_bounds_discontinuous_tail() -> None:
    current = "\n".join(f"line {index}" for index in range(10))

    assert new_output_from_snapshot("old", current, max_initial_lines=3) == "line 7\nline 8\nline 9"
