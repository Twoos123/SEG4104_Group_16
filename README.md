# SmartIntake - AI-assisted municipal 311 service request triage

SEG4105 A00 term project, Group 16 (Asad Ali, Rynak Iqbal).

A resident describes a problem in plain words. SmartIntake removes personal details, screens for
safety hazards, classifies the request, locates it, merges duplicates and opens a work order, or
sends it to an agent when it is unsure.

## Prerequisites

* Python 3.10 or newer (the Docker image uses Python 3.12)
* Optional: Docker Desktop, to build and run the app as a container

## Run it

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python etl/generate_history.py       # 1. create the synthetic legacy 311 export (CSV)
python etl/etl.py                    # 2. ETL: clean and load it into SQLite
python etl/train.py                  # 3. train and evaluate the classifier
python scripts/seed_demo.py          # 4. (optional) load 20 sample requests
uvicorn app.main:app --reload        # 5. open http://127.0.0.1:8000
```

Or with Docker: `docker build -t smartintake . && docker run -p 8000:8000 smartintake`

| Page | URL | Who uses it |
| --- | --- | --- |
| Report an issue | `/` | Resident |
| Track a request | `/track/<ticket>` | Resident |
| Review queue | `/agent` | 311 agent |
| Work orders (mock WMS) | `/workorders` | Field crews |
| KPI dashboard and routing rules | `/dashboard` | Operations supervisor |
| API docs (OpenAPI) | `/docs` | Developers |

## Quick API check

With the app running, confirm it is healthy and submit a request from the command line:

```bash
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/api/requests -H "Content-Type: application/json" -d '{"text": "Deep pothole in the right lane", "address": "245 Bank St", "channel": "WEB"}'
```

The response contains the ticket number, the predicted category, its confidence and the routing status.

## Classifier backends

* **Local model (default):** TF-IDF + logistic regression trained on the historical requests. Runs offline.
* **Hosted LLM:** set `ANTHROPIC_API_KEY` and `pip install anthropic`; requests are then classified by
  the model named in `SMARTINTAKE_LLM_MODEL`. Only redacted text is sent.

Both sit behind the same `classify(text)` interface, and the safety-keyword screen runs before either.

## Quality checks

```bash
pytest --cov --cov-report=term-missing   # dynamic analysis: 79 tests, branch coverage
ruff check .                             # static analysis: style, bugs, complexity
bandit -r app etl sim -c pyproject.toml  # static analysis: security
python scripts/benchmark.py 1000         # throughput and latency
```

## Other entry points

* `python etl/elt_load.py` - schema-on-read: land the raw CSV and run `etl/queries.sql`
* `python sim/monte_carlo.py` - CPM, PERT and Monte Carlo schedule/cost simulation

## Layout

```
app/      FastAPI app: pipeline, classifier, redaction, GIS, schema, templates
etl/      data generator, ETL job, ELT landing + query scripts, model training
sim/      project plan data, CPM and Monte Carlo simulation
tests/    pytest suite
scripts/  demo seed data and benchmark
docs/     generated reports and figures
```

All data is synthetic. No real resident or city data is used.

## Documentation

- [Software Components](docs/COMPONENTS.md)
- [System Architecture](docs/ARCHITECTURE.md)
- [Development Methodology](docs/METHODOLOGY.md)
