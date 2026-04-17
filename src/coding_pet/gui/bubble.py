from __future__ import annotations

from coding_pet.models import SessionStatus


def bubble_text_for_status(status: SessionStatus, *, max_length: int = 48) -> str:
    text = " ".join(status.summary.split())
    if len(text) <= max_length:
        return text
    return text[: max_length - 1].rstrip() + "…"
