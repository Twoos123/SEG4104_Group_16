"""PII redaction. Runs before any text is stored or sent to a classifier."""

import re

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE = re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)")
NAME = re.compile(r"\b((?i:my name is))\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)")


def redact(text: str) -> tuple[str, int]:
    """Return (redacted text, number of redactions made)."""
    count = 0

    def _sub(pattern, repl, s):
        nonlocal count
        s, n = pattern.subn(repl, s)
        count += n
        return s

    text = _sub(EMAIL, "[EMAIL]", text)
    text = _sub(PHONE, "[PHONE]", text)
    text = _sub(NAME, lambda m: f"{m.group(1)} [NAME]", text)
    return text, count
