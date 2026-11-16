import types

import pytest

from app import classifier
from app.classifier import LLMClassifier, safety_hit

CATS = {"pothole": "Pothole", "water_leak": "Water main leak"}


@pytest.mark.parametrize(
    "text,expected",
    [
        ("There is a GAS LEAK on my street", "gas leak"),
        ("downed power line across the road", "downed power line"),
        ("basement is flooding from the street", "flooding"),
        ("ordinary pothole", None),
    ],
)
def test_safety_keywords(text, expected):
    assert safety_hit(text) == expected


def test_local_classifier_predicts_with_confidence(clf):
    pred = clf.classify("huge pothole in the road damaged my tire")
    assert pred.category == "pothole"
    assert 0.5 < pred.confidence <= 1.0
    assert pred.backend == "local-tfidf-logreg"


def test_local_classifier_is_unsure_about_gibberish(clf):
    assert clf.classify("zzz qqq xxx").confidence < 0.5


class FakeClient:
    """Stands in for the hosted LLM SDK so the backend can be tested offline."""

    def __init__(self, reply):
        self.reply, self.calls = reply, []
        self.messages = types.SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return types.SimpleNamespace(content=[types.SimpleNamespace(text=self.reply)])


def test_llm_backend_parses_json_reply():
    client = FakeClient('Sure: {"category": "pothole", "confidence": 0.93}')
    pred = LLMClassifier(CATS, client=client).classify("hole in road")
    assert (pred.category, pred.confidence, pred.backend) == ("pothole", 0.93, "llm")
    assert "pothole: Pothole" in client.calls[0]["system"]
    assert client.calls[0]["messages"][0]["content"] == "hole in road"


@pytest.mark.parametrize(
    "reply",
    [
        "I cannot help with that",
        '{"category": "made_up", "confidence": 0.99}',
        '{"category": null, "confidence": 0.2}',
        '{"category": "pothole", "confidence": "high"}',
    ],
)
def test_llm_backend_fails_safe_on_bad_replies(reply):
    pred = LLMClassifier(CATS, client=FakeClient(reply)).classify("x")
    assert pred.category is None and pred.confidence == 0.0


def test_llm_confidence_is_clamped():
    pred = LLMClassifier(CATS, client=FakeClient('{"category": "pothole", "confidence": 7}')).classify("x")
    assert pred.confidence == 1.0


def test_backend_selection_defaults_to_local(env):
    assert classifier.get_classifier(CATS).name == "local-tfidf-logreg"
