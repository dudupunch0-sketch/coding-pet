from __future__ import annotations

import json
import logging
import re
import sys
from collections.abc import MutableMapping
from typing import Any, TextIO, cast

REDACTION_PATTERNS = [
    re.compile(r'(?i)(token\s*[=:]\s*["\']?)([^\s,"\']+)'),
    re.compile(r'(?i)(password\s*[=:]\s*["\']?)([^\s,"\']+)'),
    re.compile(r'(?i)(secret\s*[=:]\s*["\']?)([^\s,"\']+)'),
    re.compile(r'(?i)(api[_-]?key\s*[=:]\s*["\']?)([^\s,"\']+)'),
    re.compile(r'(?i)("token"\s*:\s*")([^"]+)'),
    re.compile(r'(?i)("password"\s*:\s*")([^"]+)'),
    re.compile(r'(?i)(authorization\s*:\s*bearer\s+)([^\s]+)'),
]


def redact_sensitive_text(message: str) -> str:
    redacted = message
    for pattern in REDACTION_PATTERNS:
        redacted = pattern.sub(r"\1[REDACTED]", redacted)
    return redacted


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "message": redact_sensitive_text(record.getMessage()),
            "component": getattr(record, "component", record.name),
            "session_id": getattr(record, "session_id", None),
            "agent_kind": getattr(record, "agent_kind", None),
            "event_type": getattr(record, "event_type", None),
        }
        return json.dumps(payload)


class TranscriptFilter(logging.Filter):
    def __init__(self, *, capture_transcripts: bool) -> None:
        super().__init__()
        self.capture_transcripts = capture_transcripts

    def filter(self, record: logging.LogRecord) -> bool:
        if self.capture_transcripts:
            return True
        return getattr(record, "event_type", None) != "transcript"


class CodingPetStreamHandler(logging.StreamHandler[TextIO]):
    pass


class ContextAdapter(logging.LoggerAdapter[logging.Logger]):
    def process(
        self,
        msg: str,
        kwargs: MutableMapping[str, Any],
    ) -> tuple[str, MutableMapping[str, Any]]:
        extra = dict(cast(dict[str, Any] | None, self.extra) or {})
        extra.update(cast(dict[str, Any], kwargs.get("extra", {})))
        kwargs["extra"] = extra
        return msg, kwargs


def setup_logging(
    *,
    stream: TextIO | None = None,
    level: str = "INFO",
    capture_transcripts: bool = False,
) -> None:
    handler = CodingPetStreamHandler(stream or sys.stderr)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(TranscriptFilter(capture_transcripts=capture_transcripts))

    root_logger = logging.getLogger()
    root_logger.handlers = [
        existing_handler
        for existing_handler in root_logger.handlers
        if not isinstance(existing_handler, CodingPetStreamHandler)
    ]
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))


def get_logger(
    component: str,
    *,
    session_id: str | None = None,
    agent_kind: str | None = None,
) -> ContextAdapter:
    logger = logging.getLogger(component)
    return ContextAdapter(
        logger,
        {
            "component": component,
            "session_id": session_id,
            "agent_kind": agent_kind,
        },
    )
