"""FastAPI application: resident form, tracking page, agent console, supervisor dashboard, JSON API."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from . import __version__, db, pipeline
from .classifier import get_classifier

templates = Jinja2Templates(directory=str(Path(__file__).with_name("templates")))
state: dict = {}


def categories(conn) -> dict[str, str]:
    return {r["code"]: r["name"] for r in conn.execute("SELECT code, name FROM category ORDER BY name")}


def classifier():
    if "classifier" not in state:
        with db.session() as conn:
            state["classifier"] = get_classifier(categories(conn))
    return state["classifier"]


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    yield
    state.clear()


app = FastAPI(title="SmartIntake", version=__version__, lifespan=lifespan)


class RequestIn(BaseModel):
    text: str = Field(min_length=5, max_length=2000)
    address: str | None = Field(default=None, max_length=200)
    channel: str = Field(default="WEB", pattern="^(WEB|EMAIL|PHONE)$")
    contact: str | None = Field(default=None, max_length=200)


# ---------------------------------------------------------------- JSON API
@app.get("/health")
def health():
    return {"status": "ok", "version": __version__, "classifier": classifier().name}


@app.post("/api/requests", status_code=201)
def api_create(body: RequestIn):
    with db.session() as conn:
        return pipeline.process_request(
            conn, classifier(), body.text, body.address, body.channel, body.contact
        )


@app.get("/api/requests/{ticket}")
def api_get(ticket: str):
    with db.session() as conn:
        row = _request_detail(conn, ticket)
    if row is None:
        raise HTTPException(404, "Ticket not found")
    return row


@app.get("/api/metrics")
def api_metrics():
    with db.session() as conn:
        return pipeline.metrics(conn)


def _request_detail(conn, ticket: str) -> dict | None:
    row = conn.execute(
        "SELECT s.ticket, s.status, s.urgency, s.text_redacted, s.address, s.confidence, "
        "s.review_reason, s.created_at, s.request_id, c.name AS category, d.name AS department, "
        "w.name AS ward, o.wo_number, o.status AS wo_status, o.due_at, o.report_count "
        "FROM service_request s LEFT JOIN category c USING(category_id) "
        "LEFT JOIN department d USING(dept_id) LEFT JOIN ward w ON w.ward_id=s.ward_id "
        "LEFT JOIN work_order o ON o.work_order_id=s.work_order_id WHERE s.ticket=?",
        (ticket,),
    ).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------- Resident pages
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    with db.session() as conn:
        streets = [r["name"] for r in conn.execute("SELECT name FROM street ORDER BY name")]
    return templates.TemplateResponse(request, "home.html", {"streets": streets})


@app.post("/requests")
def submit(
    text: str = Form(...), address: str = Form(""), contact: str = Form(""), channel: str = Form("WEB")
):
    try:
        with db.session() as conn:
            result = pipeline.process_request(
                conn, classifier(), text, address or None, channel, contact or None
            )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return RedirectResponse(f"/track/{result['ticket']}", status_code=303)


@app.get("/track/{ticket}", response_class=HTMLResponse)
def track(request: Request, ticket: str):
    with db.session() as conn:
        row = _request_detail(conn, ticket)
        if row is None:
            raise HTTPException(404, "Ticket not found")
        notes = conn.execute(
            "SELECT * FROM notification WHERE request_id=? ORDER BY notification_id", (row["request_id"],)
        ).fetchall()
    return templates.TemplateResponse(request, "track.html", {"r": row, "notes": notes})


# ---------------------------------------------------------------- Agent console
@app.get("/agent", response_class=HTMLResponse)
def agent_queue(request: Request, error: str = ""):
    with db.session() as conn:
        queue = conn.execute(
            "SELECT s.*, c.code AS predicted FROM service_request s "
            "LEFT JOIN category c USING(category_id) WHERE s.status='NEEDS_REVIEW' "
            "ORDER BY (s.urgency='URGENT') DESC, s.request_id"
        ).fetchall()
        cats = categories(conn)
    return templates.TemplateResponse(request, "agent.html", {"queue": queue, "cats": cats, "error": error})


@app.post("/agent/{request_id}/resolve")
def agent_resolve(request_id: int, category: str = Form(...), address: str = Form("")):
    try:
        with db.session() as conn:
            pipeline.resolve_review(conn, request_id, category, address)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        return RedirectResponse(f"/agent?error={exc}", status_code=303)
    return RedirectResponse("/agent", status_code=303)


# ---------------------------------------------------------------- Work orders (mock WMS)
@app.get("/workorders", response_class=HTMLResponse)
def work_orders(request: Request):
    with db.session() as conn:
        rows = conn.execute(
            "SELECT o.*, c.name AS category, d.name AS department, w.name AS ward "
            "FROM work_order o JOIN category c USING(category_id) "
            "JOIN department d ON d.dept_id=o.dept_id LEFT JOIN ward w ON w.ward_id=o.ward_id "
            "ORDER BY o.work_order_id DESC LIMIT 100"
        ).fetchall()
    return templates.TemplateResponse(request, "workorders.html", {"rows": rows})


@app.post("/workorders/{work_order_id}/advance")
def work_order_advance(work_order_id: int):
    try:
        with db.session() as conn:
            pipeline.advance_work_order(conn, work_order_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return RedirectResponse("/workorders", status_code=303)


# ---------------------------------------------------------------- Supervisor dashboard
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    with db.session() as conn:
        m = pipeline.metrics(conn)
        settings = {r["key"]: r["value"] for r in conn.execute("SELECT * FROM setting")}
        recent = conn.execute(
            "SELECT s.ticket, s.status, s.confidence, s.urgency, c.name AS category "
            "FROM service_request s LEFT JOIN category c USING(category_id) "
            "ORDER BY s.request_id DESC LIMIT 12"
        ).fetchall()
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"m": m, "settings": settings, "recent": recent, "backend": classifier().name},
    )


@app.post("/dashboard/rules")
def update_rules(confidence_threshold: float = Form(...), duplicate_radius_m: float = Form(...)):
    if not 0.5 <= confidence_threshold <= 0.99:
        raise HTTPException(400, "Confidence threshold must be between 0.50 and 0.99")
    if not 5 <= duplicate_radius_m <= 500:
        raise HTTPException(400, "Duplicate radius must be between 5 and 500 metres")
    with db.session() as conn:
        db.set_setting(conn, "confidence_threshold", confidence_threshold)
        db.set_setting(conn, "duplicate_radius_m", duplicate_radius_m)
    return RedirectResponse("/dashboard", status_code=303)
