from __future__ import annotations

import hashlib


def snapshot_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="surrogatepass")).hexdigest()


def _bounded_tail(lines: list[str], max_lines: int) -> str:
    if max_lines <= 0:
        return ""
    return "\n".join(lines[-max_lines:])


def new_output_from_snapshot(
    previous: str | None,
    current: str,
    *,
    max_initial_lines: int = 50,
) -> str:
    if previous == current:
        return ""
    current_lines = current.splitlines()
    if previous is None:
        return _bounded_tail(current_lines, max_initial_lines)
    previous_lines = previous.splitlines()
    max_overlap = min(len(previous_lines), len(current_lines))
    for overlap in range(max_overlap, 0, -1):
        if previous_lines[-overlap:] == current_lines[:overlap]:
            return "\n".join(current_lines[overlap:])
    return _bounded_tail(current_lines, max_initial_lines)
