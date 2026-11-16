"""Request classification.

Two interchangeable backends share one interface (`classify(text) -> Prediction`):

* LLMClassifier   - calls a hosted large language model (used when an API key is configured)
* LocalClassifier - TF-IDF + logistic regression trained on historical requests (offline fallback)

A safety-keyword screen runs before either backend, so urgent hazards never depend on a model.
"""

import json
import os
import pickle
from dataclasses import dataclass

from . import config


@dataclass(frozen=True)
class Prediction:
    category: str | None
    confidence: float
    backend: str


def safety_hit(text: str) -> str | None:
    """Return the first safety keyword found in the text, or None."""
    lowered = text.lower()
    for kw in config.SAFETY_KEYWORDS:
        if kw in lowered:
            return kw
    return None


class LocalClassifier:
    name = "local-tfidf-logreg"

    def __init__(self, pipeline):
        self.pipeline = pipeline

    @classmethod
    def load(cls, path=None) -> "LocalClassifier":
        path = path or config.model_path()
        with open(path, "rb") as fh:
            # Model file is produced locally by etl/train.py; it is never downloaded or user-supplied.
            return cls(pickle.load(fh))  # nosec B301

    def classify(self, text: str) -> Prediction:
        probs = self.pipeline.predict_proba([text])[0]
        best = int(probs.argmax())
        return Prediction(str(self.pipeline.classes_[best]), float(probs[best]), self.name)


class LLMClassifier:
    """Hosted LLM backend. Only redacted text is ever sent."""

    name = "llm"

    def __init__(self, categories: dict[str, str], client=None, model: str | None = None):
        self.categories = categories
        self.model = model or config.LLM_MODEL
        if client is None:
            import anthropic  # imported lazily so the dependency stays optional

            client = anthropic.Anthropic()
        self.client = client

    def _system_prompt(self) -> str:
        cats = "\n".join(f"- {code}: {name}" for code, name in self.categories.items())
        return (
            "You triage municipal 311 service requests. Choose exactly one category code from "
            f"this list:\n{cats}\n\nReply with JSON only, for example "
            '{"category": "pothole", "confidence": 0.93}. confidence is your probability (0 to 1) '
            "that the category is correct. If nothing fits, use null and a low confidence."
        )

    def classify(self, text: str) -> Prediction:
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=100,
            system=self._system_prompt(),
            messages=[{"role": "user", "content": text}],
        )
        return self.parse(resp.content[0].text)

    def parse(self, raw: str) -> Prediction:
        try:
            data = json.loads(raw[raw.index("{") : raw.rindex("}") + 1])
            category = data.get("category")
            confidence = float(data.get("confidence", 0.0))
        except (ValueError, TypeError, AttributeError):
            return Prediction(None, 0.0, self.name)
        if category not in self.categories:
            return Prediction(None, 0.0, self.name)
        return Prediction(category, max(0.0, min(1.0, confidence)), self.name)


def get_classifier(categories: dict[str, str]):
    """Pick the backend: hosted LLM if a key is configured, else the local model."""
    if os.environ.get(config.LLM_API_KEY_ENV):
        try:
            return LLMClassifier(categories)
        except ImportError:
            pass
    return LocalClassifier.load()
