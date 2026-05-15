from __future__ import annotations

from dataclasses import dataclass

from coding_pet.transcripts.model import TranscriptEvent


@dataclass(frozen=True, slots=True)
class TranscriptViewRow:
    timestamp: str
    direction: str
    text: str


def build_transcript_rows(
    events: list[TranscriptEvent] | tuple[TranscriptEvent, ...],
) -> list[TranscriptViewRow]:
    return [
        TranscriptViewRow(
            timestamp=event.ts.strftime("%H:%M:%S"),
            direction=event.direction,
            text=event.text,
        )
        for event in events
    ]
