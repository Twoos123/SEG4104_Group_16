"""Schema-on-write ETL: legacy 311 CSV export -> cleaned `historical_request` table.

Extract   read the raw CSV as-is
Transform parse dates, map legacy labels to category codes, redact personal details, geocode,
          drop blanks / unknown labels / bad dates / exact duplicates
Load      insert typed, constrained rows; write rejects to a CSV; record the run in `etl_run`
"""

import csv
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config, db, gis  # noqa: E402
from app.redact import redact  # noqa: E402

DATE_FORMATS = ("%Y-%m-%d %H:%M", "%m/%d/%Y %I:%M %p", "%d-%b-%Y %H:%M")
LABEL_RULES = [  # first matching rule wins; order matters
    (r"pot ?hole", "pothole"),
    (r"sidewalk", "sidewalk_damage"),
    (r"snow|ice", "snow_removal"),
    (r"dumping", "illegal_dumping"),
    (r"garbage|collection", "missed_garbage"),
    (r"street ?light", "streetlight_out"),
    (r"signal|traffic", "traffic_signal"),
    (r"tree|branch", "fallen_tree"),
    (r"park", "park_maintenance"),
    (r"graffiti", "graffiti"),
    (r"noise", "noise_complaint"),
    (r"water", "water_leak"),
]


def extract(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def parse_date(value: str) -> datetime | None:
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    return None


def map_label(label: str) -> str | None:
    lowered = label.lower()
    for pattern, code in LABEL_RULES:
        if re.search(pattern, lowered):
            return code
    return None


def transform(rows: list[dict], conn) -> tuple[list[tuple], list[dict], dict]:
    """Return (clean rows ready to load, rejected rows with a reason, counters)."""
    cat_ids = {r["code"]: r["category_id"] for r in conn.execute("SELECT code, category_id FROM category")}
    clean, rejects, seen = [], [], set()
    stats = {"duplicates_removed": 0, "pii_redactions": 0, "ungeocoded": 0}
    for i, row in enumerate(rows, start=2):  # row 1 is the CSV header

        def reject(reason, row=row, i=i):
            rejects.append({"source_row": i, "reason": reason, **row})

        text = (row.get("description") or "").strip()
        if not text:
            reject("blank description")
            continue
        when = parse_date(row.get("received") or "")
        if when is None:
            reject("unparseable date")
            continue
        code = map_label(row.get("type") or "")
        if code is None:
            reject("unknown category label")
            continue
        key = (row["received"], row["type"], text, row.get("location"))
        if key in seen:
            stats["duplicates_removed"] += 1
            continue
        seen.add(key)
        redacted, n = redact(text)
        stats["pii_redactions"] += n
        address = (row.get("location") or "").strip() or None
        loc = gis.geocode(conn, address)
        if loc is None:
            stats["ungeocoded"] += 1
        channel = (row.get("channel") or "phone").strip().upper()
        clean.append(
            (
                i,
                when.strftime("%Y-%m-%dT%H:%M:00"),
                channel,
                redacted,
                cat_ids[code],
                address,
                loc.lat if loc else None,
                loc.lon if loc else None,
                loc.ward_id if loc else None,
            )
        )
    return clean, rejects, stats


def load(conn, clean: list[tuple]) -> int:
    conn.execute("DELETE FROM historical_request")  # full refresh keeps the job idempotent
    conn.executemany(
        "INSERT INTO historical_request(source_row,created_at,channel,text_redacted,category_id,"
        "address,lat,lon,ward_id) VALUES (?,?,?,?,?,?,?,?,?)",
        clean,
    )
    return len(clean)


def run(source: Path | None = None, db_file=None) -> dict:
    source = source or config.DATA_DIR / "legacy_311_export.csv"
    db.init_db(db_file)
    started = datetime.now().isoformat(timespec="seconds")
    raw = extract(source)
    with db.session(db_file) as conn:
        clean, rejects, stats = transform(raw, conn)
        loaded = load(conn, clean)
        conn.execute(
            "INSERT INTO etl_run(started_at,source_file,rows_extracted,rows_loaded,rows_rejected,"
            "duplicates_removed,pii_redactions) VALUES (?,?,?,?,?,?,?)",
            (
                started,
                source.name,
                len(raw),
                loaded,
                len(rejects),
                stats["duplicates_removed"],
                stats["pii_redactions"],
            ),
        )
    reject_file = source.with_name("etl_rejects.csv")
    if rejects:
        with open(reject_file, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rejects[0]))
            writer.writeheader()
            writer.writerows(rejects)
    reasons = {}
    for r in rejects:
        reasons[r["reason"]] = reasons.get(r["reason"], 0) + 1
    summary = {
        "rows_extracted": len(raw),
        "rows_loaded": loaded,
        "rows_rejected": len(rejects),
        "reject_reasons": reasons,
        **stats,
    }
    print(summary)
    return summary


if __name__ == "__main__":
    run()
