# Software Components

SmartIntake is a single Python package set (`app`, `etl`, `sim`, `scripts`, `tests`) deployed as one
FastAPI process with a SQLite database file. This document lists every top-level module, where it
lives, what it is responsible for and what it depends on.

## 1. Component Inventory

### Runtime application (`app/`)

| Component / Module | Directory / File Path | Primary Responsibility | Key Dependencies |
| :--- | :--- | :--- | :--- |
| Presentation / UI | `/app/templates/` (`base`, `home`, `track`, `agent`, `workorders`, `dashboard`) | Server-rendered pages for the resident form, ticket tracking, agent review queue, work orders and the supervisor dashboard | Jinja2 |
| Web / API layer | `/app/main.py` | Defines the FastAPI app, HTML routes and the JSON API; validates input (`RequestIn`); maps domain errors to HTTP status codes; opens one database session per request | FastAPI, Pydantic, python-multipart, `app.pipeline`, `app.db`, `app.classifier` |
| Triage pipeline (core logic) | `/app/pipeline.py` | Runs each request through redact, safety screen, classify, geocode, de-duplicate and route; resolves agent reviews; advances work orders; computes dashboard KPIs | `app.redact`, `app.classifier`, `app.gis`, `app.db` |
| Classifier | `/app/classifier.py` | One `classify(text) -> Prediction` interface with two backends: `LocalClassifier` (TF-IDF + logistic regression) and `LLMClassifier` (hosted LLM); also the safety-keyword screen | scikit-learn model file `data/model.pkl`; optional `anthropic` SDK |
| PII redaction | `/app/redact.py` | Replaces e-mail addresses, phone numbers and self-introduced names with placeholders before text is stored or classified | Python `re` |
| GIS | `/app/gis.py` | Geocodes a street address to coordinates and a ward using the `street` table; haversine distance for duplicate detection | `street` table (stands in for the city GIS service) |
| Data access / storage | `/app/db.py`, `/app/schema.sql` | SQLite connection and transactional `session()`; creates the schema; seeds departments, categories, wards, streets and routing settings | SQLite (`sqlite3`), `app.config` |
| Configuration | `/app/config.py` | File locations, default routing rules, safety keywords and LLM settings, each overridable by an environment variable | Environment variables |

### Data preparation (`etl/`)

| Component / Module | Directory / File Path | Primary Responsibility | Key Dependencies |
| :--- | :--- | :--- | :--- |
| History generator | `/etl/generate_history.py` | Produces a synthetic, deliberately messy "legacy 311 export" CSV | `app.config`, `app.db` |
| ETL job (schema-on-write) | `/etl/etl.py` | Parses dates, maps legacy labels to category codes, redacts, geocodes, drops bad rows and loads `historical_request`; logs each run in `etl_run` | `app.db`, `app.gis`, `app.redact` |
| ELT landing (schema-on-read) | `/etl/elt_load.py`, `/etl/queries.sql` | Lands the raw CSV untouched in `raw_311_landing` and shapes it with SQL views and analysis queries | SQLite |
| Model training | `/etl/train.py` | Trains and evaluates the local classifier on `historical_request`; writes `data/model.pkl` and `data/model_metrics.json` | scikit-learn, `app.db` |

### Supporting code

| Component / Module | Directory / File Path | Primary Responsibility | Key Dependencies |
| :--- | :--- | :--- | :--- |
| Project simulation | `/sim/plan.py`, `/sim/monte_carlo.py` | Project plan data; critical path (CPM), PERT and Monte Carlo schedule and cost simulation; writes `docs/sim_results.json` and charts | NumPy, Matplotlib |
| Scripts | `/scripts/seed_demo.py`, `/scripts/benchmark.py`, `/scripts/collect_facts.py` | Loads sample requests for the demo, measures pipeline throughput and latency, gathers measured figures for the report | `app.pipeline`, `app.classifier` |
| Test suite | `/tests/` | Unit and API tests for the pipeline, classifier, redaction, GIS, ETL and HTTP routes | pytest, pytest-cov, httpx (FastAPI `TestClient`) |
| Container build | `/Dockerfile`, `/.dockerignore` | Builds a runnable image: installs dependencies, generates data, runs the ETL, trains the model, starts Uvicorn on port 8000 | Docker, `python:3.12-slim` |

### Database tables (`app/schema.sql`)

| Table | Purpose |
| :--- | :--- |
| `department`, `category`, `ward`, `street` | Reference data: who handles what, service-level hours, and the street gazetteer |
| `service_request` | One row per resident request: redacted text, location, predicted category, confidence, status |
| `work_order` | Work created for a department; several duplicate requests can share one work order |
| `agent_review` | Audit record of each human review: predicted versus final category |
| `notification` | Messages recorded for the resident (the prototype logs instead of sending) |
| `setting` | Routing rules a supervisor can change at run time |
| `historical_request`, `etl_run` | Cleaned training data and the ETL run log |

## 2. External Interfaces & APIs

### Input Interfaces

| Interface | Used by | Description |
| :--- | :--- | :--- |
| `POST /api/requests` | Other systems | JSON body `text` (5 to 2000 characters), optional `address`, `channel` (`WEB`, `EMAIL` or `PHONE`), optional `contact`; returns `201` with the triage result |
| `POST /requests` | Resident (web form) | Form fields `text`, `address`, `contact`, `channel`; redirects to the tracking page |
| `POST /agent/{request_id}/resolve` | 311 agent | Confirms or corrects the category and address of a flagged request |
| `POST /workorders/{work_order_id}/advance` | Field crews (mock WMS) | Moves a work order to its next status |
| `POST /dashboard/rules` | Operations supervisor | Updates the confidence threshold (0.50 to 0.99) and duplicate radius (5 to 500 m) |
| Legacy CSV file | ETL / ELT jobs | `received`, `channel`, `type`, `description`, `location` columns of the historical export |
| Environment variables | Operator | `SMARTINTAKE_DATA_DIR`, `SMARTINTAKE_DB`, `SMARTINTAKE_MODEL`, `SMARTINTAKE_LLM_MODEL`, `ANTHROPIC_API_KEY` |
| Command line | Developer | `python etl/*.py`, `python sim/monte_carlo.py`, `python scripts/benchmark.py [n]` |

### Output Interfaces

| Interface | Description |
| :--- | :--- |
| `GET /api/requests/{ticket}` | JSON detail of one request, including its work order and due time |
| `GET /api/metrics` | JSON KPIs: automation rate, processing time, duplicates merged, review backlog |
| `GET /health` | Service status, version and the active classifier backend |
| `GET /docs` | OpenAPI (Swagger) documentation generated by FastAPI |
| HTML pages | `/`, `/track/{ticket}`, `/agent`, `/workorders`, `/dashboard` |
| Database writes | `service_request`, `work_order`, `agent_review`, `notification`, `setting` in `data/smartintake.db` |
| Generated files | `data/model.pkl`, `data/model_metrics.json`, ETL reject CSV, `docs/sim_results.json`, `docs/figures/*.png`, `docs/reports/*` |
| Hosted LLM call (optional) | Redacted request text sent to the configured model when `ANTHROPIC_API_KEY` is set |
