import csv
from datetime import datetime

import pytest

from app import db
from etl import elt_load, etl

HEADER = ["received", "channel", "type", "description", "location"]
ROWS = [
    ["2025-03-14 09:12", "phone", "POTHOLE", "deep pothole, call 613-555-0142", "245 Bank St"],
    ["03/15/2025 9:12 AM", "web", "Street Light", "light is out", "near the mall"],
    ["16-Mar-2025 10:00", "email", "Tree Down", "tree across the road", "12 Elgin St"],
    ["2025-03-14 09:12", "phone", "POTHOLE", "deep pothole, call 613-555-0142", "245 Bank St"],  # exact dup
    ["2025-03-17 08:00", "web", "Pothole", "", "1 Bank St"],  # blank
    ["n/a", "web", "Pothole", "pothole", "1 Bank St"],  # bad date
    ["2025-03-18 08:00", "web", "General Inquiry", "question", "1 Bank St"],  # unknown label
]


@pytest.mark.parametrize(
    "value,expected",
    [
        ("2025-03-14 09:12", datetime(2025, 3, 14, 9, 12)),
        ("03/14/2025 9:12 PM", datetime(2025, 3, 14, 21, 12)),
        ("14-Mar-2025 09:12", datetime(2025, 3, 14, 9, 12)),
        ("n/a", None),
        ("", None),
        ("00/00/0000", None),
    ],
)
def test_parse_date(value, expected):
    assert etl.parse_date(value) == expected


@pytest.mark.parametrize(
    "label,code",
    [
        ("POTHOLE", "pothole"),
        ("pot hole", "pothole"),
        ("Street Light", "streetlight_out"),
        ("TRAFFIC LIGHT", "traffic_signal"),
        ("tree/branch", "fallen_tree"),
        ("SNOW/ICE", "snow_removal"),
        ("Dumping (illegal)", "illegal_dumping"),
        ("garbage - missed", "missed_garbage"),
        ("Parks - Maintenance", "park_maintenance"),
        ("WATER - LEAK", "water_leak"),
        ("Other", None),
        ("???", None),
    ],
)
def test_map_label(label, code):
    assert etl.map_label(label) == code


@pytest.fixture()
def source(env):
    path = env / "legacy.csv"
    with open(path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(HEADER)
        writer.writerows(ROWS)
    return path


def test_etl_run_cleans_loads_and_logs(source):
    summary = etl.run(source)
    assert summary["rows_extracted"] == 7 and summary["rows_loaded"] == 3
    assert summary["rows_rejected"] == 3 and summary["duplicates_removed"] == 1
    assert summary["reject_reasons"] == {
        "blank description": 1,
        "unparseable date": 1,
        "unknown category label": 1,
    }
    assert summary["pii_redactions"] == 1 and summary["ungeocoded"] == 1
    with db.session() as conn:
        rows = conn.execute("SELECT * FROM historical_request ORDER BY source_row").fetchall()
        assert rows[0]["created_at"] == "2025-03-14T09:12:00" and "[PHONE]" in rows[0]["text_redacted"]
        assert rows[0]["channel"] == "PHONE" and rows[0]["ward_id"] == 2
        assert rows[1]["lat"] is None
        assert conn.execute("SELECT rows_loaded FROM etl_run").fetchone()[0] == 3
    with open(source.with_name("etl_rejects.csv"), newline="") as fh:
        rejects = list(csv.DictReader(fh))
    assert [r["source_row"] for r in rejects] == ["6", "7", "8"]


def test_etl_is_idempotent(source):
    etl.run(source)
    etl.run(source)
    with db.session() as conn:
        assert conn.execute("SELECT COUNT(*) FROM historical_request").fetchone()[0] == 3
        assert conn.execute("SELECT COUNT(*) FROM etl_run").fetchone()[0] == 2


def test_elt_lands_raw_rows_and_queries_run(source, env):
    lake = env / "lake.db"
    assert elt_load.land(source, lake) == 7
    report = elt_load.run_queries(lake)
    assert "Q1 Data quality profile" in report and "7 | 1 | 1 | 1" in report
    assert "pothole" in report and "Q6 Label sprawl" in report
