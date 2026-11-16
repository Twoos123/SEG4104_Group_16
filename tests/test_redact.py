import pytest

from app.redact import redact


@pytest.mark.parametrize(
    "raw,token",
    [
        ("email me at jane.doe+311@example.com please", "[EMAIL]"),
        ("call 613-555-0142", "[PHONE]"),
        ("call (613) 555-0142 now", "[PHONE]"),
        ("text +1 613.555.0142", "[PHONE]"),
        ("my name is Alex Morgan and I live here", "[NAME]"),
    ],
)
def test_redacts_pii(raw, token):
    out, n = redact(raw)
    assert token in out and n >= 1


def test_original_values_are_gone():
    out, n = redact("My name is Alex Morgan, 613-555-0142, alex@example.com")
    assert "Alex" not in out and "0142" not in out and "example.com" not in out
    assert n == 3


def test_leaves_addresses_and_plain_text_alone():
    text = "Pothole at 245 Bank St, reported 3 times"
    assert redact(text) == (text, 0)
