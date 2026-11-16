import pytest
from fastapi.testclient import TestClient

from app import main

POTHOLE = "huge pothole in the road damaged my tire"


@pytest.fixture()
def client(env):
    main.state.clear()
    with TestClient(main.app) as c:
        yield c
    main.state.clear()


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["classifier"] == "local-tfidf-logreg"


def test_api_create_and_fetch(client):
    created = client.post("/api/requests", json={"text": POTHOLE, "address": "245 Bank St"})
    assert created.status_code == 201
    ticket = created.json()["ticket"]
    detail = client.get(f"/api/requests/{ticket}").json()
    assert detail["status"] == "ROUTED" and detail["department"] == "Roads & Sidewalks"
    assert detail["wo_number"].startswith("WO-")


@pytest.mark.parametrize(
    "payload",
    [
        {"text": "hey"},
        {"text": POTHOLE, "channel": "FAX"},
        {"address": "245 Bank St"},
        {"text": "x" * 2001},
    ],
)
def test_api_validation(client, payload):
    assert client.post("/api/requests", json=payload).status_code == 422


def test_api_unknown_ticket(client):
    assert client.get("/api/requests/SR-0000-000000").status_code == 404
    assert client.get("/track/SR-0000-000000").status_code == 404


def test_resident_form_flow(client):
    assert "Report an issue" in client.get("/").text
    resp = client.post(
        "/requests",
        data={"text": POTHOLE, "address": "245 Bank St", "contact": "a@example.com"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    page = client.get(resp.headers["location"]).text
    assert "ROUTED" in page and "Pothole" in page and "Work order" in page


def test_agent_console_flow(client):
    client.post("/requests", data={"text": "there is a gas leak here", "address": "near the mall"})
    page = client.get("/agent").text
    assert "URGENT" in page and "Safety keyword" in page
    bad = client.post(
        "/agent/1/resolve", data={"category": "water_leak", "address": ""}, follow_redirects=False
    )
    assert "error=" in bad.headers["location"]
    ok = client.post(
        "/agent/1/resolve", data={"category": "water_leak", "address": "12 Elgin St"}, follow_redirects=False
    )
    assert ok.headers["location"] == "/agent"
    assert "Nothing is waiting" in client.get("/agent").text
    assert client.post("/agent/99/resolve", data={"category": "pothole"}).status_code == 404


def test_work_order_lifecycle(client):
    client.post("/api/requests", json={"text": POTHOLE, "address": "245 Bank St"})
    assert "WO-" in client.get("/workorders").text
    for _ in range(3):
        assert client.post("/workorders/1/advance", follow_redirects=False).status_code == 303
    assert client.post("/workorders/1/advance").status_code == 409
    assert client.post("/workorders/99/advance").status_code == 404
    assert "COMPLETED" in client.get("/workorders").text


def test_dashboard_and_rules(client):
    client.post("/api/requests", json={"text": POTHOLE, "address": "245 Bank St"})
    assert "Supervisor dashboard" in client.get("/dashboard").text
    assert client.get("/api/metrics").json()["automation_rate"] == 1.0
    ok = client.post(
        "/dashboard/rules",
        data={"confidence_threshold": 0.99, "duplicate_radius_m": 80},
        follow_redirects=False,
    )
    assert ok.status_code == 303
    second = client.post("/api/requests", json={"text": POTHOLE, "address": "400 Bank St"}).json()
    assert second["status"] == "NEEDS_REVIEW"
    for bad in (
        {"confidence_threshold": 0.2, "duplicate_radius_m": 50},
        {"confidence_threshold": 0.8, "duplicate_radius_m": 9999},
    ):
        assert client.post("/dashboard/rules", data=bad).status_code == 400
