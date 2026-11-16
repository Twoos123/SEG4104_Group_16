import pickle

import pytest

from app import db
from etl.train import build_pipeline

TRAIN = {
    "pothole": [
        "deep pothole in the road",
        "huge pothole damaged my tire",
        "pot hole in the lane",
        "crater in the pavement",
        "pothole near the bus stop",
    ],
    "streetlight_out": [
        "streetlight is out",
        "street lamp is dark",
        "streetlight flickering at night",
        "lamp post light burned out",
        "streetlight not working",
    ],
    "missed_garbage": [
        "garbage was not picked up",
        "recycling bin skipped",
        "green bin not collected",
        "trash still at the curb",
        "truck missed our garbage",
    ],
    "fallen_tree": [
        "tree fell across the road",
        "large branch blocking sidewalk",
        "tree came down in storm",
        "big limb fell on a car",
        "branches down on the path",
    ],
    "noise_complaint": [
        "loud music at night",
        "dog barking all night",
        "party noise next door",
        "construction noise at dawn",
        "loud bass every weekend",
    ],
    "water_leak": [
        "water bubbling through pavement",
        "water main break",
        "water gushing from hydrant",
        "pipe burst spraying water",
        "leak at the water valve",
    ],
}


@pytest.fixture(scope="session")
def model_file(tmp_path_factory):
    texts, labels = [], []
    for label, examples in TRAIN.items():
        for _ in range(4):  # repeat so min_df is satisfied
            texts += examples
            labels += [label] * len(examples)
    path = tmp_path_factory.mktemp("model") / "model.pkl"
    with open(path, "wb") as fh:
        pickle.dump(build_pipeline().fit(texts, labels), fh)
    return path


@pytest.fixture()
def env(tmp_path, monkeypatch, model_file):
    """Point the app at an empty temporary database and the small test model."""
    monkeypatch.setenv("SMARTINTAKE_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("SMARTINTAKE_MODEL", str(model_file))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    db.init_db()
    return tmp_path


@pytest.fixture()
def conn(env):
    with db.session() as c:
        yield c


@pytest.fixture()
def clf(env):
    from app.classifier import LocalClassifier

    return LocalClassifier.load()
