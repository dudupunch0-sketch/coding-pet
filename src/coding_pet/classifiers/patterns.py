from __future__ import annotations

import re

FAILED_PATTERNS = (
    re.compile(r"(?i)\btraceback\b"),
    re.compile(r"(?i)\bexception\b"),
    re.compile(r"(?i)\berror:"),
    re.compile(r"(?i)\bfailed\b"),
    re.compile(r"(?i)command not found"),
    re.compile(r"(?i)segmentation fault"),
    re.compile(r"(?i)permission denied"),
    re.compile(r"오류"),
    re.compile(r"실패"),
)

PERMISSION_PATTERNS = (
    re.compile(r"(?i)\ballow\b"),
    re.compile(r"(?i)\bapprove\b"),
    re.compile(r"(?i)\bapproval required\b"),
    re.compile(r"(?i)permission"),
    re.compile(r"(?i)do you want to proceed"),
    re.compile(r"(?i)run this command"),
    re.compile(r"(?i)allow codex"),
    re.compile(r"(?i)codex.*run"),
    re.compile(r"실행할까요"),
    re.compile(r"승인"),
    re.compile(r"권한"),
    re.compile(r"허용"),
)

CHOICE_PATTERNS = (
    re.compile(r"(?i)\bselect\b"),
    re.compile(r"(?i)\bchoose\b"),
    re.compile(r"(?i)pick one"),
    re.compile(r"(?m)^\s*1[\).]\s+.+\n\s*2[\).]\s+"),
    re.compile(r"(?m)^\s*\[1\]\s+.+\n\s*\[2\]\s+"),
    re.compile(r"(?i)\by/n\b"),
    re.compile(r"(?i)yes/no"),
    re.compile(r"선택"),
    re.compile(r"번호를 입력"),
)

INPUT_PATTERNS = (
    re.compile(r"(?i)need clarification"),
    re.compile(r"(?i)please clarify"),
    re.compile(r"(?i)what should i"),
    re.compile(r"(?i)would you like"),
    re.compile(r"(?i)do you want"),
    re.compile(r"(?i)can you confirm"),
    re.compile(r"어떤"),
    re.compile(r"확인"),
    re.compile(r"계속할까요"),
    re.compile(r"입력"),
    re.compile(r"알려주세요"),
)

COMPLETED_PATTERNS = (
    re.compile(r"(?i)task completed"),
    re.compile(r"(?i)\bdone\b"),
    re.compile(r"완료"),
)

RUNNING_PATTERNS = (
    re.compile(r"(?i)\breading\b"),
    re.compile(r"(?i)\banalyzing\b"),
    re.compile(r"(?i)\brunning\b"),
    re.compile(r"(?i)\bgenerating\b"),
    re.compile(r"(?i)\bexecuting\b"),
    re.compile(r"(?i)\bsearching\b"),
    re.compile(r"(?i)\bfetching\b"),
    re.compile(r"(?i)\bprocessing\b"),
)
