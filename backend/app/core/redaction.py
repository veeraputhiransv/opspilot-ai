"""Redact obvious PII before it reaches logs.

Operators still see customer text in the console, because that is the evidence.
Log files should not keep a second copy of email addresses or card-like numbers.
"""

import re

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_CARD = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
_INJECTION = (
    "ignore previous",
    "ignore all",
    "disregard previous",
    "system prompt",
    "you are now",
    "override policy",
    "bypass approval",
    "skip approval",
)


def redact(value: str) -> str:
    cleaned = _EMAIL.sub("[email]", value)
    return _CARD.sub("[number]", cleaned)


def looks_like_injection(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in _INJECTION)
