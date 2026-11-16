"""The triage pipeline: redact -> safety screen -> classify -> geocode -> de-duplicate -> route."""

import time
from datetime import datetime, timedelta, timezone

from . import db, gis
from .classifier import Prediction, safety_hit
from .redact import redact

PRIORITY_ORDER = ["LOW", "MEDIUM", "HIGH", "URGENT"]


def now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(dt: datetime) -> str:
    return dt.isoformat()


def _category(conn, code: str):
    return conn.execute("SELECT * FROM category WHERE code=?", (code,)).fetchone()


def notify(conn, request_id: int, message: str, contact: str | None) -> None:
    """Record a resident notification (the prototype logs instead of sending email/SMS)."""
    channel = "NONE" if not contact else ("EMAIL" if "@" in contact else "SMS")
    conn.execute(
        "INSERT INTO notification(request_id,channel,message,sent_at) VALUES (?,?,?,?)",
        (request_id, channel, message, iso(now())),
    )


def find_duplicate(conn, category_id: int, lat: float, lon: float, at: datetime):
    """Return the open work order for the same category within the configured radius, if any."""
    radius = db.get_setting(conn, "duplicate_radius_m")
    window = db.get_setting(conn, "duplicate_window_days")
    since = iso(at - timedelta(days=window))
    rows = conn.execute(
        "SELECT * FROM work_order WHERE category_id=? AND status!='COMPLETED' "
        "AND created_at>=? AND lat IS NOT NULL",
        (category_id, since),
    ).fetchall()
    best, best_d = None, radius
    for row in rows:
        d = gis.haversine_m(lat, lon, row["lat"], row["lon"])
        if d <= best_d:
            best, best_d = row, d
    return best


def create_work_order(conn, cat, loc: gis.Location, urgency: str, at: datetime) -> int:
    priority = "URGENT" if urgency == "URGENT" else cat["default_priority"]
    hours = min(cat["sla_hours"], 4) if priority == "URGENT" else cat["sla_hours"]
    cur = conn.execute(
        "INSERT INTO work_order(category_id,dept_id,ward_id,lat,lon,priority,created_at,due_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (
            cat["category_id"],
            cat["dept_id"],
            loc.ward_id,
            loc.lat,
            loc.lon,
            priority,
            iso(at),
            iso(at + timedelta(hours=hours)),
        ),
    )
    wo_id = cur.lastrowid
    conn.execute(
        "UPDATE work_order SET wo_number=? WHERE work_order_id=?", (f"WO-{at.year}-{wo_id:06d}", wo_id)
    )
    return wo_id


def route(conn, request_id: int, cat, loc: gis.Location, urgency: str, contact, at: datetime) -> str:
    """De-duplicate, then create or attach a work order. Returns the final request status."""
    dup = find_duplicate(conn, cat["category_id"], loc.lat, loc.lon, at)
    if dup is not None:
        first = conn.execute(
            "SELECT request_id FROM service_request WHERE work_order_id=? AND status='ROUTED' "
            "ORDER BY request_id LIMIT 1",
            (dup["work_order_id"],),
        ).fetchone()
        conn.execute(
            "UPDATE work_order SET report_count=report_count+1 WHERE work_order_id=?", (dup["work_order_id"],)
        )
        conn.execute(
            "UPDATE service_request SET status='DUPLICATE', duplicate_of=?, work_order_id=? "
            "WHERE request_id=?",
            (first["request_id"] if first else None, dup["work_order_id"], request_id),
        )
        notify(conn, request_id, f"Already reported: linked to {dup['wo_number']}.", contact)
        return "DUPLICATE"
    wo_id = create_work_order(conn, cat, loc, urgency, at)
    conn.execute(
        "UPDATE service_request SET status='ROUTED', work_order_id=? WHERE request_id=?", (wo_id, request_id)
    )
    wo = conn.execute("SELECT wo_number FROM work_order WHERE work_order_id=?", (wo_id,)).fetchone()
    notify(conn, request_id, f"Work order {wo['wo_number']} created for {cat['name']}.", contact)
    return "ROUTED"


def process_request(
    conn,
    classifier,
    text: str,
    address: str | None,
    channel: str = "WEB",
    contact: str | None = None,
    at: datetime | None = None,
) -> dict:
    """Run one request through the whole pipeline and persist the result."""
    if not text or not text.strip():
        raise ValueError("Request text is required")
    if channel not in ("WEB", "EMAIL", "PHONE"):
        raise ValueError(f"Unknown channel: {channel}")
    started = time.perf_counter()
    at = at or now()

    redacted, _ = redact(text.strip())
    hazard = safety_hit(redacted)
    urgency = "URGENT" if hazard else "ROUTINE"

    # The model still suggests a category for urgent requests, but a person always confirms it.
    pred: Prediction = classifier.classify(redacted)
    cat = _category(conn, pred.category) if pred.category else None
    loc = gis.geocode(conn, address)
    threshold = db.get_setting(conn, "confidence_threshold")

    reason = None
    if hazard:
        reason = f"Safety keyword: {hazard}"
    elif cat is None or pred.confidence < threshold:
        reason = f"Low confidence ({pred.confidence:.2f} < {threshold:.2f})"
    elif loc is None:
        reason = "Address could not be located"

    cur = conn.execute(
        "INSERT INTO service_request(channel,text_redacted,address,lat,lon,ward_id,category_id,"
        "confidence,urgency,status,review_reason,contact,classifier_backend,auto_routed,created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            channel,
            redacted,
            address,
            loc.lat if loc else None,
            loc.lon if loc else None,
            loc.ward_id if loc else None,
            cat["category_id"] if cat else None,
            pred.confidence,
            urgency,
            "NEEDS_REVIEW",
            reason,
            contact,
            pred.backend,
            0 if reason else 1,
            iso(at),
        ),
    )
    request_id = cur.lastrowid
    ticket = f"SR-{at.year}-{request_id:06d}"
    conn.execute("UPDATE service_request SET ticket=? WHERE request_id=?", (ticket, request_id))

    if reason:
        status = "NEEDS_REVIEW"
        notify(conn, request_id, f"Request {ticket} received and is being reviewed.", contact)
    else:
        status = route(conn, request_id, cat, loc, urgency, contact, at)

    elapsed_ms = (time.perf_counter() - started) * 1000
    conn.execute("UPDATE service_request SET processed_ms=? WHERE request_id=?", (elapsed_ms, request_id))
    return {
        "request_id": request_id,
        "ticket": ticket,
        "status": status,
        "category": pred.category,
        "confidence": round(pred.confidence, 4),
        "urgency": urgency,
        "review_reason": reason,
        "processed_ms": round(elapsed_ms, 2),
    }


def resolve_review(
    conn, request_id: int, category_code: str, address: str | None, agent: str = "agent"
) -> str:
    """An agent confirms or corrects a flagged request; it then continues down the pipeline."""
    req = conn.execute("SELECT * FROM service_request WHERE request_id=?", (request_id,)).fetchone()
    if req is None:
        raise LookupError(f"Request {request_id} not found")
    if req["status"] != "NEEDS_REVIEW":
        raise ValueError(f"Request {request_id} is not awaiting review")
    cat = _category(conn, category_code)
    if cat is None:
        raise ValueError(f"Unknown category: {category_code}")
    address = (address or req["address"] or "").strip()
    loc = gis.geocode(conn, address)
    if loc is None:
        raise ValueError("A valid street address is required to route the request")
    conn.execute(
        "INSERT INTO agent_review(request_id,predicted_category_id,final_category_id,agent,reason,"
        "resolved_at) VALUES (?,?,?,?,?,?)",
        (request_id, req["category_id"], cat["category_id"], agent, req["review_reason"], iso(now())),
    )
    conn.execute(
        "UPDATE service_request SET category_id=?, address=?, lat=?, lon=?, ward_id=? WHERE request_id=?",
        (cat["category_id"], address, loc.lat, loc.lon, loc.ward_id, request_id),
    )
    return route(conn, request_id, cat, loc, req["urgency"], req["contact"], now())


WO_TRANSITIONS = {"OPEN": "ASSIGNED", "ASSIGNED": "IN_PROGRESS", "IN_PROGRESS": "COMPLETED"}


def advance_work_order(conn, work_order_id: int) -> str:
    """Move a work order to its next status (simulates the WMS) and notify every reporter."""
    wo = conn.execute("SELECT * FROM work_order WHERE work_order_id=?", (work_order_id,)).fetchone()
    if wo is None:
        raise LookupError(f"Work order {work_order_id} not found")
    nxt = WO_TRANSITIONS.get(wo["status"])
    if nxt is None:
        raise ValueError("Work order is already completed")
    done = iso(now()) if nxt == "COMPLETED" else None
    conn.execute(
        "UPDATE work_order SET status=?, completed_at=? WHERE work_order_id=?", (nxt, done, work_order_id)
    )
    for req in conn.execute(
        "SELECT request_id, contact FROM service_request WHERE work_order_id=?", (work_order_id,)
    ).fetchall():
        notify(
            conn,
            req["request_id"],
            f"{wo['wo_number']} is now {nxt.replace('_', ' ').lower()}.",
            req["contact"],
        )
        if nxt == "COMPLETED":
            conn.execute(
                "UPDATE service_request SET status='CLOSED' WHERE request_id=?", (req["request_id"],)
            )
    return nxt


def metrics(conn) -> dict:
    """KPIs for the supervisor dashboard."""
    total = conn.execute("SELECT COUNT(*) c FROM service_request").fetchone()["c"]
    auto = conn.execute("SELECT COUNT(*) c FROM service_request WHERE auto_routed=1").fetchone()["c"]
    row = conn.execute(
        "SELECT AVG(processed_ms) avg_ms, MAX(processed_ms) max_ms FROM service_request"
    ).fetchone()
    reviewed = conn.execute("SELECT COUNT(*) c FROM agent_review").fetchone()["c"]
    corrected = conn.execute(
        "SELECT COUNT(*) c FROM agent_review WHERE predicted_category_id IS NULL "
        "OR predicted_category_id != final_category_id"
    ).fetchone()["c"]
    by_status = {
        r["status"]: r["c"]
        for r in conn.execute("SELECT status, COUNT(*) c FROM service_request GROUP BY status")
    }
    by_category = [
        dict(r)
        for r in conn.execute(
            "SELECT c.name, COUNT(*) n FROM service_request s JOIN category c USING(category_id) "
            "GROUP BY c.name ORDER BY n DESC"
        )
    ]
    return {
        "total_requests": total,
        "auto_routed": auto,
        "automation_rate": round(auto / total, 4) if total else 0.0,
        "avg_processing_ms": round(row["avg_ms"] or 0.0, 2),
        "max_processing_ms": round(row["max_ms"] or 0.0, 2),
        "duplicates_merged": by_status.get("DUPLICATE", 0),
        "awaiting_review": by_status.get("NEEDS_REVIEW", 0),
        "open_work_orders": conn.execute(
            "SELECT COUNT(*) c FROM work_order WHERE status!='COMPLETED'"
        ).fetchone()["c"],
        "reviews_completed": reviewed,
        "reviews_corrected": corrected,
        "by_status": by_status,
        "by_category": by_category,
    }
