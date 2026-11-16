"""Schema-on-read ELT: land the raw CSV untouched, then shape it with SQL at query time.

Load      every column of the legacy export is stored as TEXT in `raw_311_landing` (no cleaning)
Transform `etl/queries.sql` defines views that parse and classify the raw text when queried
"""

import csv
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config  # noqa: E402

QUERIES = Path(__file__).with_name("queries.sql")


def land(source: Path, lake: Path) -> int:
    conn = sqlite3.connect(lake)
    conn.execute("DROP TABLE IF EXISTS raw_311_landing")
    conn.execute(
        "CREATE TABLE raw_311_landing (received TEXT, channel TEXT, type TEXT, "
        "description TEXT, location TEXT, _loaded_at TEXT DEFAULT CURRENT_TIMESTAMP)"
    )
    with open(source, newline="", encoding="utf-8") as fh:
        rows = [
            (r["received"], r["channel"], r["type"], r["description"], r["location"])
            for r in csv.DictReader(fh)
        ]
    conn.executemany(
        "INSERT INTO raw_311_landing(received,channel,type,description,location) VALUES (?,?,?,?,?)", rows
    )
    conn.commit()
    conn.close()
    return len(rows)


def run_queries(lake: Path) -> str:
    """Run every statement in queries.sql; return a text report of each SELECT's result."""
    conn = sqlite3.connect(lake)
    out = []
    title = ""
    for block in QUERIES.read_text().split(";"):
        lines = [ln for ln in block.strip().splitlines()]
        comments = [ln[2:].strip() for ln in lines if ln.startswith("--")]
        sql = "\n".join(ln for ln in lines if not ln.startswith("--")).strip()
        if comments:
            title = comments[0]
        if not sql:
            continue
        cur = conn.execute(sql)
        if cur.description:
            cols = [d[0] for d in cur.description]
            out.append(f"## {title}")
            out.append(" | ".join(cols))
            out.extend(" | ".join(str(v) for v in row) for row in cur.fetchall())
            out.append("")
    conn.commit()
    conn.close()
    return "\n".join(out)


def run(source: Path | None = None, lake: Path | None = None) -> str:
    source = source or config.DATA_DIR / "legacy_311_export.csv"
    lake = lake or config.DATA_DIR / "lake.db"
    n = land(source, lake)
    report = f"Landed {n} raw rows into {lake.name}\n\n" + run_queries(lake)
    (config.DATA_DIR / "elt_results.txt").write_text(report)
    print(report)
    return report


if __name__ == "__main__":
    run()
