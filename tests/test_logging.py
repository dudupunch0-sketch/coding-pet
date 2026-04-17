from __future__ import annotations

import json
import logging
from io import StringIO

from coding_pet.logging import get_logger, redact_sensitive_text, setup_logging


def test_setup_logging_emits_structured_json() -> None:
    stream = StringIO()
    setup_logging(stream=stream, level="INFO")

    logger = get_logger("daemon.monitor", session_id="sess-1", agent_kind="opencode")
    logger.info("monitor-ready")

    payload = json.loads(stream.getvalue().strip())
    assert payload["message"] == "monitor-ready"
    assert payload["component"] == "daemon.monitor"
    assert payload["session_id"] == "sess-1"
    assert payload["agent_kind"] == "opencode"
    assert payload["level"] == "INFO"


def test_redact_sensitive_text_masks_common_secret_formats() -> None:
    redacted = redact_sensitive_text(
        'token=abc123secret password=hunter2 api_key: xyz987 '
        '"token":"json-secret" Authorization: Bearer super-token'
    )

    assert "abc123secret" not in redacted
    assert "hunter2" not in redacted
    assert "xyz987" not in redacted
    assert "json-secret" not in redacted
    assert "super-token" not in redacted
    assert redacted.count("[REDACTED]") >= 5


def test_debug_transcript_capture_can_be_disabled() -> None:
    stream = StringIO()
    setup_logging(stream=stream, level="DEBUG", capture_transcripts=False)

    logger = get_logger("daemon.monitor")
    logger.debug("transcript line", extra={"event_type": "transcript"})
    logger.info("normal line")

    lines = [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]
    assert [line["message"] for line in lines] == ["normal line"]
    assert logging.getLogger().level == logging.DEBUG


def test_setup_logging_preserves_non_coding_pet_handlers() -> None:
    existing_handler = logging.NullHandler()
    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    root_logger.handlers = [existing_handler]

    try:
        stream = StringIO()
        setup_logging(stream=stream, level="INFO")
        assert existing_handler in logging.getLogger().handlers
    finally:
        root_logger.handlers = original_handlers


def test_setup_logging_replaces_previous_coding_pet_handlers() -> None:
    original_handlers = list(logging.getLogger().handlers)
    previous_stream = StringIO()
    new_stream = StringIO()

    try:
        setup_logging(stream=previous_stream, level="INFO")
        setup_logging(stream=new_stream, level="INFO")

        logger = get_logger("daemon.monitor")
        logger.info("hello")

        assert previous_stream.getvalue() == ""
        assert "hello" in new_stream.getvalue()
    finally:
        root_logger = logging.getLogger()
        root_logger.handlers = original_handlers
