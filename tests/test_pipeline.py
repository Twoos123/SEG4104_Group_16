from datetime import timedelta

import pytest

from app import db, pipeline

POTHOLE = "huge pothole in the road damaged my tire"


def submit(conn, clf, text=POTHOLE, address="245 Bank St", **kw):
    return pipeline.process_request(conn, clf, text, address, **kw)


def test_confident_request_is_routed_automatically(conn, clf):
    r = submit(conn, clf, contact="resident@example.com")
    assert r["status"] == "ROUTED" and r["category"] == "pothole" and r["review_reason"] is None
    row = conn.execute("SELECT * FROM service_request WHERE request_id=?", (r["request_id"],)).fetchone()
    assert row["auto_routed"] == 1 and row["ward_id"] == 2 and row["ticket"].startswith("SR-")
    wo = conn.execute("SELECT * FROM work_order WHERE work_order_id=?", (row["work_order_id"],)).fetchone()
    assert wo["dept_id"] == 1 and wo["priority"] == "MEDIUM" and wo["status"] == "OPEN"
    note = conn.execute("SELECT * FROM notification WHERE request_id=?", (r["request_id"],)).fetchone()
    assert note["channel"] == "EMAIL" and wo["wo_number"] in note["message"]


def test_pii_is_redacted_before_storage(conn, clf):
    r = submit(conn, clf, text=POTHOLE + ". My name is Alex Morgan, call 613-555-0142")
    stored = conn.execute(
        "SELECT text_redacted FROM service_request WHERE request_id=?", (r["request_id"],)
    ).fetchone()[0]
    assert "Alex" not in stored and "0142" not in stored and "[PHONE]" in stored


def test_safety_keyword_always_goes_to_a_person(conn, clf):
    r = submit(conn, clf, text="pothole and I can smell gas, maybe a gas leak")
    assert r["status"] == "NEEDS_REVIEW" and r["urgency"] == "URGENT"
    assert "Safety keyword" in r["review_reason"]
    assert conn.execute("SELECT COUNT(*) FROM work_order").fetchone()[0] == 0


def test_low_confidence_goes_to_review(conn, clf):
    r = submit(conn, clf, text="something is wrong around here somewhere")
    assert r["status"] == "NEEDS_REVIEW" and "Low confidence" in r["review_reason"]


def test_unknown_address_goes_to_review(conn, clf):
    r = submit(conn, clf, address="near the mall")
    assert r["status"] == "NEEDS_REVIEW" and r["review_reason"] == "Address could not be located"


def test_nearby_same_category_is_merged_as_duplicate(conn, clf):
    first = submit(conn, clf, address="245 Bank St")
    second = submit(conn, clf, address="250 Bank St")  # about 5.5 m away
    assert second["status"] == "DUPLICATE"
    assert conn.execute("SELECT COUNT(*) FROM work_order").fetchone()[0] == 1
    assert conn.execute("SELECT report_count FROM work_order").fetchone()[0] == 2
    dup = conn.execute(
        "SELECT duplicate_of FROM service_request WHERE request_id=?", (second["request_id"],)
    ).fetchone()[0]
    assert dup == first["request_id"]


def test_far_away_or_other_category_is_not_a_duplicate(conn, clf):
    submit(conn, clf, address="245 Bank St")
    assert submit(conn, clf, address="600 Bank St")["status"] == "ROUTED"  # about 390 m away
    assert (
        submit(conn, clf, text="streetlight is out and dark at night", address="245 Bank St")["status"]
        == "ROUTED"
    )
    assert conn.execute("SELECT COUNT(*) FROM work_order").fetchone()[0] == 3


def test_old_work_orders_are_outside_the_duplicate_window(conn, clf):
    old = pipeline.now() - timedelta(days=30)
    submit(conn, clf, at=old)
    assert submit(conn, clf)["status"] == "ROUTED"


def test_completed_work_order_does_not_absorb_new_reports(conn, clf):
    r = submit(conn, clf)
    wo_id = conn.execute(
        "SELECT work_order_id FROM service_request WHERE request_id=?", (r["request_id"],)
    ).fetchone()[0]
    for expected in ("ASSIGNED", "IN_PROGRESS", "COMPLETED"):
        assert pipeline.advance_work_order(conn, wo_id) == expected
    assert (
        conn.execute("SELECT status FROM service_request WHERE request_id=?", (r["request_id"],)).fetchone()[
            0
        ]
        == "CLOSED"
    )
    with pytest.raises(ValueError):
        pipeline.advance_work_order(conn, wo_id)
    assert submit(conn, clf)["status"] == "ROUTED"


def test_supervisor_threshold_changes_routing(conn, clf):
    db.set_setting(conn, "confidence_threshold", 0.99)
    assert submit(conn, clf)["status"] == "NEEDS_REVIEW"


def test_agent_resolves_review_and_correction_is_recorded(conn, clf):
    r = submit(conn, clf, text="there is a gas leak smell by the water main break", address="near the mall")
    with pytest.raises(ValueError):  # still no usable address
        pipeline.resolve_review(conn, r["request_id"], "water_leak", "")
    status = pipeline.resolve_review(conn, r["request_id"], "water_leak", "12 Elgin St", agent="asad")
    assert status == "ROUTED"
    wo = conn.execute("SELECT priority, dept_id FROM work_order").fetchone()
    assert wo["priority"] == "URGENT" and wo["dept_id"] == 6
    review = conn.execute("SELECT * FROM agent_review").fetchone()
    assert review["agent"] == "asad" and review["final_category_id"] is not None
    with pytest.raises(ValueError):  # cannot resolve twice
        pipeline.resolve_review(conn, r["request_id"], "water_leak", "12 Elgin St")


def test_resolve_rejects_unknown_request_and_category(conn, clf):
    with pytest.raises(LookupError):
        pipeline.resolve_review(conn, 999, "pothole", "12 Elgin St")
    r = submit(conn, clf, address="nowhere")
    with pytest.raises(ValueError):
        pipeline.resolve_review(conn, r["request_id"], "not_a_category", "12 Elgin St")


@pytest.mark.parametrize("text,channel", [("", "WEB"), ("   ", "WEB"), (POTHOLE, "FAX")])
def test_invalid_input_is_rejected(conn, clf, text, channel):
    with pytest.raises(ValueError):
        pipeline.process_request(conn, clf, text, "245 Bank St", channel)


def test_metrics(conn, clf):
    submit(conn, clf)
    submit(conn, clf, address="250 Bank St")
    submit(conn, clf, text="gas leak", address="12 Elgin St")
    m = pipeline.metrics(conn)
    assert m["total_requests"] == 3 and m["auto_routed"] == 2
    assert m["automation_rate"] == pytest.approx(0.6667, abs=1e-4)
    assert m["duplicates_merged"] == 1 and m["awaiting_review"] == 1 and m["open_work_orders"] == 1
