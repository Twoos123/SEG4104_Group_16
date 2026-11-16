"""Train and evaluate the local classifier on the cleaned historical requests."""

import json
import pickle
import sys
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config, db  # noqa: E402


def build_pipeline():
    return make_pipeline(
        TfidfVectorizer(lowercase=True, ngram_range=(1, 2), min_df=2, sublinear_tf=True),
        LogisticRegression(max_iter=1000, C=10.0),
    )


def evaluate(model, x_test, y_test, threshold: float) -> dict:
    probs = model.predict_proba(x_test)
    preds = model.classes_[probs.argmax(axis=1)]
    conf = probs.max(axis=1)
    confident = conf >= threshold
    report = classification_report(y_test, preds, output_dict=True, zero_division=0)
    return {
        "test_rows": len(y_test),
        "accuracy_all": round(float(accuracy_score(y_test, preds)), 4),
        "threshold": threshold,
        "auto_route_share": round(float(confident.mean()), 4),
        "accuracy_auto_routed": round(
            float(accuracy_score([y for y, c in zip(y_test, confident, strict=True) if c], preds[confident])),
            4,
        ),
        "wrong_and_auto_routed_share": round(
            float(
                sum(1 for y, p, c in zip(y_test, preds, confident, strict=True) if c and y != p) / len(y_test)
            ),
            4,
        ),
        "per_category": {
            k: {
                "precision": round(v["precision"], 3),
                "recall": round(v["recall"], 3),
                "support": int(v["support"]),
            }
            for k, v in report.items()
            if isinstance(v, dict) and "avg" not in k
        },
    }


def run(db_file=None, model_file=None, seed: int = 42) -> dict:
    with db.session(db_file) as conn:
        rows = conn.execute(
            "SELECT h.text_redacted, c.code FROM historical_request h JOIN category c USING(category_id)"
        ).fetchall()
    if len(rows) < 100:
        raise RuntimeError("Not enough historical rows; run etl/etl.py first")
    texts = [r["text_redacted"] for r in rows]
    labels = [r["code"] for r in rows]
    x_train, x_test, y_train, y_test = train_test_split(
        texts, labels, test_size=0.2, random_state=seed, stratify=labels
    )
    model = build_pipeline().fit(x_train, y_train)
    result = evaluate(model, x_test, y_test, config.DEFAULT_CONFIDENCE_THRESHOLD)
    result["train_rows"] = len(y_train)
    result["sweep"] = [
        {
            k: v
            for k, v in evaluate(model, x_test, y_test, t).items()
            if k in ("threshold", "auto_route_share", "accuracy_auto_routed")
        }
        for t in (0.5, 0.6, 0.7, 0.8, 0.9, 0.95)
    ]
    model_file = Path(model_file) if model_file else config.model_path()
    model_file.parent.mkdir(parents=True, exist_ok=True)
    with open(model_file, "wb") as fh:
        pickle.dump(model, fh)
    (model_file.parent / "model_metrics.json").write_text(json.dumps(result, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k != "per_category"}, indent=2))
    return result


if __name__ == "__main__":
    run()
