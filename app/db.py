"""SQLite access layer and reference-data seeding."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from . import config

SCHEMA_FILE = Path(__file__).with_name("schema.sql")

DEPARTMENTS = [
    (1, "Roads & Sidewalks", "roads@city.example"),
    (2, "Solid Waste", "waste@city.example"),
    (3, "Traffic & Lighting", "traffic@city.example"),
    (4, "Parks & Forestry", "parks@city.example"),
    (5, "By-law Services", "bylaw@city.example"),
    (6, "Water Services", "water@city.example"),
]

# code, name, dept_id, sla_hours, default_priority
CATEGORIES = [
    ("pothole", "Pothole", 1, 72, "MEDIUM"),
    ("sidewalk_damage", "Sidewalk damage", 1, 120, "LOW"),
    ("snow_removal", "Snow / ice removal", 1, 24, "HIGH"),
    ("missed_garbage", "Missed garbage or recycling pickup", 2, 48, "MEDIUM"),
    ("illegal_dumping", "Illegal dumping", 2, 96, "LOW"),
    ("streetlight_out", "Streetlight out", 3, 120, "LOW"),
    ("traffic_signal", "Traffic signal problem", 3, 8, "HIGH"),
    ("fallen_tree", "Fallen tree or branch", 4, 24, "HIGH"),
    ("park_maintenance", "Park maintenance", 4, 168, "LOW"),
    ("graffiti", "Graffiti", 5, 168, "LOW"),
    ("noise_complaint", "Noise complaint", 5, 48, "LOW"),
    ("water_leak", "Water main leak", 6, 12, "HIGH"),
]

WARDS = [
    (i, n)
    for i, n in enumerate(
        [
            "Riverside",
            "Centretown",
            "Glebe Park",
            "Westboro",
            "Kanata Lakes",
            "Orleans East",
            "Barrhaven",
            "Alta Vista",
        ],
        start=1,
    )
]

# name, ward_id, base_lat, base_lon
STREETS = [
    ("Bank St", 2, 45.4120, -75.6900),
    ("Elgin St", 2, 45.4180, -75.6890),
    ("Somerset St", 2, 45.4140, -75.7010),
    ("Laurier Ave", 2, 45.4210, -75.6950),
    ("Rideau St", 1, 45.4290, -75.6830),
    ("Sussex Dr", 1, 45.4390, -75.6950),
    ("Montreal Rd", 1, 45.4420, -75.6400),
    ("St Laurent Blvd", 1, 45.4300, -75.6380),
    ("Fifth Ave", 3, 45.4000, -75.6880),
    ("Holmwood Ave", 3, 45.3970, -75.6860),
    ("Bronson Ave", 3, 45.4010, -75.6990),
    ("Sunnyside Ave", 3, 45.3930, -75.6830),
    ("Richmond Rd", 4, 45.3920, -75.7560),
    ("Churchill Ave", 4, 45.3890, -75.7530),
    ("Carling Ave", 4, 45.3800, -75.7600),
    ("Island Park Dr", 4, 45.3960, -75.7430),
    ("Terry Fox Dr", 5, 45.3120, -75.9200),
    ("Kanata Ave", 5, 45.3100, -75.9100),
    ("March Rd", 5, 45.3400, -75.9150),
    ("Campeau Dr", 5, 45.3160, -75.9050),
    ("Tenth Line Rd", 6, 45.4650, -75.4850),
    ("Innes Rd", 6, 45.4480, -75.5150),
    ("Jeanne d'Arc Blvd", 6, 45.4750, -75.5200),
    ("Trim Rd", 6, 45.4800, -75.4600),
    ("Strandherd Dr", 7, 45.2750, -75.7500),
    ("Greenbank Rd", 7, 45.2900, -75.7600),
    ("Fallowfield Rd", 7, 45.2980, -75.7800),
    ("Longfields Dr", 7, 45.2800, -75.7350),
    ("Alta Vista Dr", 8, 45.3850, -75.6600),
    ("Smyth Rd", 8, 45.4000, -75.6500),
    ("Heron Rd", 8, 45.3780, -75.6700),
    ("Walkley Rd", 8, 45.3680, -75.6500),
]


def connect(path=None) -> sqlite3.Connection:
    path = Path(path) if path else config.db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def session(path=None):
    """Open a connection, commit on success, roll back on error, always close."""
    conn = connect(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(path=None) -> None:
    """Create tables (idempotent) and seed reference data."""
    with session(path) as conn:
        conn.executescript(SCHEMA_FILE.read_text())
        conn.executemany("INSERT OR IGNORE INTO department VALUES (?,?,?)", DEPARTMENTS)
        conn.executemany(
            "INSERT OR IGNORE INTO category(code,name,dept_id,sla_hours,default_priority) VALUES (?,?,?,?,?)",
            CATEGORIES,
        )
        conn.executemany("INSERT OR IGNORE INTO ward VALUES (?,?)", WARDS)
        conn.executemany(
            "INSERT OR IGNORE INTO street(name,ward_id,base_lat,base_lon) VALUES (?,?,?,?)", STREETS
        )
        defaults = {
            "confidence_threshold": config.DEFAULT_CONFIDENCE_THRESHOLD,
            "duplicate_radius_m": config.DEFAULT_DUPLICATE_RADIUS_M,
            "duplicate_window_days": config.DEFAULT_DUPLICATE_WINDOW_DAYS,
        }
        conn.executemany(
            "INSERT OR IGNORE INTO setting VALUES (?,?)", [(k, str(v)) for k, v in defaults.items()]
        )


def get_setting(conn, key: str) -> float:
    row = conn.execute("SELECT value FROM setting WHERE key=?", (key,)).fetchone()
    if row is None:
        raise KeyError(key)
    return float(row["value"])


def set_setting(conn, key: str, value: float) -> None:
    conn.execute(
        "INSERT INTO setting(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )
