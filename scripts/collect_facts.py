"""Gather every measured number the Phase 2 report quotes into docs/facts.json.

Run last, after the ETL, training, simulation and test steps.
"""

import csv
import json
import re
import sqlite3
import subprocess  # nosec B404 - runs this project's own tools with fixed arguments
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import config  # noqa: E402
from scripts import benchmark  # noqa: E402
from sim import plan  # noqa: E402

DESCRIPTIONS = {
    "department": {
        "dept_id": "Department identifier",
        "name": "Department name",
        "email": "Dispatch mailbox for the department",
    },
    "category": {
        "category_id": "Category identifier",
        "code": "Short code used by the classifier",
        "name": "Name shown to residents and agents",
        "dept_id": "Department that handles this category",
        "sla_hours": "Target hours to complete a work order",
        "default_priority": "Priority given to routine requests: LOW, MEDIUM or HIGH",
    },
    "ward": {"ward_id": "Ward identifier", "name": "Ward name"},
    "street": {
        "street_id": "Street identifier",
        "name": "Street name as held by the GIS",
        "ward_id": "Ward the street belongs to",
        "base_lat": "Latitude of house number 0",
        "base_lon": "Longitude of the street",
    },
    "service_request": {
        "request_id": "Request identifier",
        "ticket": "Public ticket number, e.g. SR-2026-000123",
        "channel": "How it arrived: WEB, EMAIL or PHONE",
        "text_redacted": "Description with personal details removed",
        "address": "Address as given by the resident",
        "lat": "Latitude from geocoding",
        "lon": "Longitude from geocoding",
        "ward_id": "Ward from geocoding",
        "category_id": "Predicted, then agent-confirmed, category",
        "confidence": "Classifier confidence, 0 to 1",
        "urgency": "ROUTINE, or URGENT when a safety keyword is present",
        "status": "NEEDS_REVIEW, ROUTED, DUPLICATE or CLOSED",
        "review_reason": "Why a person had to review it",
        "duplicate_of": "First request for the same problem, if a duplicate",
        "work_order_id": "Work order that fulfils the request",
        "contact": "Email or mobile for updates (optional)",
        "classifier_backend": "Which backend classified it (llm or local model)",
        "processed_ms": "Pipeline processing time in milliseconds",
        "auto_routed": "1 if routed with no human touch, else 0",
        "created_at": "When it was received (UTC, ISO 8601)",
    },
    "work_order": {
        "work_order_id": "Work order identifier",
        "wo_number": "Public number, e.g. WO-2026-000045",
        "category_id": "Type of work",
        "dept_id": "Department assigned",
        "ward_id": "Ward of the job",
        "lat": "Latitude of the job",
        "lon": "Longitude of the job",
        "priority": "LOW, MEDIUM, HIGH or URGENT",
        "status": "OPEN, ASSIGNED, IN_PROGRESS or COMPLETED",
        "report_count": "Number of resident reports merged into it",
        "created_at": "When it was opened",
        "due_at": "Created time plus the category SLA",
        "completed_at": "When the crew finished",
    },
    "agent_review": {
        "review_id": "Review identifier",
        "request_id": "Request that was reviewed",
        "predicted_category_id": "What the classifier suggested",
        "final_category_id": "What the agent chose",
        "agent": "Agent who resolved it",
        "reason": "Why it was flagged",
        "resolved_at": "When it was resolved",
    },
    "notification": {
        "notification_id": "Notification identifier",
        "request_id": "Request it concerns",
        "channel": "EMAIL, SMS or NONE (no contact given)",
        "message": "Text sent to the resident",
        "sent_at": "When it was sent",
    },
    "historical_request": {
        "hist_id": "Row identifier",
        "source_row": "Line number in the legacy CSV (lineage)",
        "created_at": "Received date, normalised to ISO 8601",
        "channel": "WEB, EMAIL or PHONE",
        "text_redacted": "Description with personal details removed",
        "category_id": "Category mapped from the legacy label",
        "address": "Address as recorded",
        "lat": "Latitude, null if not geocoded",
        "lon": "Longitude, null if not geocoded",
        "ward_id": "Ward, null if not geocoded",
    },
    "etl_run": {
        "run_id": "Run identifier",
        "started_at": "When the job started",
        "source_file": "File that was loaded",
        "rows_extracted": "Rows read from the source",
        "rows_loaded": "Rows written to historical_request",
        "rows_rejected": "Rows written to the rejects file",
        "duplicates_removed": "Exact duplicate rows dropped",
        "pii_redactions": "Personal details removed from free text",
    },
    "setting": {
        "key": "Rule name, e.g. confidence_threshold",
        "value": "Current value set by the supervisor",
    },
}


def data_dictionary() -> list[dict]:
    conn = sqlite3.connect(config.db_path())
    out = []
    for table, cols in DESCRIPTIONS.items():
        fks = {r[3]: f"{r[2]}.{r[4]}" for r in conn.execute(f"PRAGMA foreign_key_list({table})")}  # nosec B608
        info = conn.execute(f"PRAGMA table_info({table})").fetchall()  # nosec B608
        if {r[1] for r in info} != set(cols):
            raise RuntimeError(f"data dictionary out of date for {table}")
        for _, name, ctype, notnull, _, pk in info:
            key = "PK" if pk else ("FK > " + fks[name] if name in fks else "")
            out.append(
                {
                    "table": table,
                    "column": name,
                    "type": ctype,
                    "key": key,
                    "required": "Yes" if notnull or pk else "No",
                    "description": cols[name],
                }
            )
    return out


def run(cmd: list[str]) -> str:
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False).stdout  # nosec B603


def main() -> None:
    conn = sqlite3.connect(config.db_path())
    conn.row_factory = sqlite3.Row
    etl = dict(conn.execute("SELECT * FROM etl_run ORDER BY run_id DESC LIMIT 1").fetchone())
    reasons: dict[str, int] = {}
    with open(config.DATA_DIR / "etl_rejects.csv", newline="") as fh:
        for row in csv.DictReader(fh):
            reasons[row["reason"]] = reasons.get(row["reason"], 0) + 1
    etl["reject_reasons"] = reasons
    etl["ungeocoded"] = conn.execute("SELECT COUNT(*) FROM historical_request WHERE lat IS NULL").fetchone()[
        0
    ]

    pytest_out = run([sys.executable, "-m", "pytest", "--cov", "--cov-report=term-missing"])
    (ROOT / "docs/reports/pytest_coverage.txt").write_text(pytest_out)
    coverage = [
        {"module": m.group(1), "stmts": int(m.group(2)), "miss": int(m.group(3)), "cover": m.group(6)}
        for m in re.finditer(r"^(\S+\.py|TOTAL)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+%)", pytest_out, re.M)
    ]
    passed = re.search(r"(\d+) passed", pytest_out)
    per_file = {}
    for line in run([sys.executable, "-m", "pytest", "--collect-only", "-q"]).splitlines():
        m = re.match(r"(tests/\S+\.py)(?:::|: (\d+))", line)
        if m:
            per_file[m.group(1)] = int(m.group(2)) if m.group(2) else per_file.get(m.group(1), 0) + 1

    bandit_out = run(
        [
            sys.executable,
            "-m",
            "bandit",
            "-r",
            "app",
            "etl",
            "sim",
            "scripts",
            "-c",
            "pyproject.toml",
            "-f",
            "json",
        ]
    )
    (ROOT / "docs/reports/bandit.json").write_text(bandit_out)
    bandit = json.loads(bandit_out)
    totals = bandit["metrics"]["_totals"]
    ruff_out = run([sys.executable, "-m", "ruff", "check", "."])
    (ROOT / "docs/reports/ruff_final.txt").write_text(ruff_out)
    first = (ROOT / "docs/reports/ruff_first_pass.txt").read_text()
    first_rules: dict[str, int] = {}
    for m in re.finditer(r": ([A-Z]+\d+) ", first):
        first_rules[m.group(1)] = first_rules.get(m.group(1), 0) + 1
    loc = {
        d: sum(len(p.read_text().splitlines()) for p in (ROOT / d).rglob("*.py"))
        for d in ("app", "etl", "sim", "tests", "scripts")
    }

    facts = {
        "etl": etl,
        "model": json.loads((config.DATA_DIR / "model_metrics.json").read_text()),
        "sim": json.loads((ROOT / "docs/sim_results.json").read_text()),
        "budget": json.loads((ROOT / "docs/budget_baseline.json").read_text()),
        "benchmark": benchmark.main(1000),
        "tests": {"passed": int(passed.group(1)), "per_file": per_file, "coverage": coverage},
        "bandit": {
            "loc": totals["loc"],
            "low": totals["SEVERITY.LOW"],
            "medium": totals["SEVERITY.MEDIUM"],
            "high": totals["SEVERITY.HIGH"],
            "suppressed": totals["nosec"] + totals["skipped_tests"],
            "issues": [
                {
                    "id": r["test_id"],
                    "text": r["issue_text"],
                    "file": r["filename"],
                    "line": r["line_number"],
                    "severity": r["issue_severity"],
                }
                for r in bandit["results"]
            ],
        },
        "ruff": {
            "first_pass": first_rules,
            "first_total": sum(first_rules.values()),
            "final_clean": "All checks passed" in ruff_out,
        },
        "loc": loc,
        "elt": (config.DATA_DIR / "elt_results.txt").read_text(),
        "queries_sql": (ROOT / "etl/queries.sql").read_text(),
        "data_dictionary": data_dictionary(),
        "activities": {
            k: {"name": v[0], "preds": v[1], "amb": v[2], "labour": v[3], "other": v[4]}
            for k, v in plan.ACTIVITIES.items()
        },
        "risks": {
            k: {
                "category": v[0],
                "risk": v[1],
                "p": v[2],
                "cost": v[3],
                "impact": v[4],
                "pscore": plan.probability_score(v[2]),
                "activity": v[5],
                "delay": v[6],
                "strategy": v[7],
                "response": v[8],
                "owner": v[9],
            }
            for k, v in plan.RISKS.items()
        },
        "plan": {
            "cloud_build": plan.CLOUD_BUILD,
            "cloud_ops": plan.CLOUD_OPERATIONS,
            "contingency": plan.CONTINGENCY_RESERVE,
            "mgmt": plan.MANAGEMENT_RESERVE,
        },
    }
    (ROOT / "docs/facts.json").write_text(json.dumps(facts, indent=1))
    print({k: facts[k] for k in ("tests", "bandit", "ruff", "loc", "benchmark")})


if __name__ == "__main__":
    main()
