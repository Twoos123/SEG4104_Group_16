-- SmartIntake relational schema (schema-on-write target of the ETL job and the live system)
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS department (
    dept_id     INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    email       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS category (
    category_id      INTEGER PRIMARY KEY,
    code             TEXT NOT NULL UNIQUE,
    name             TEXT NOT NULL,
    dept_id          INTEGER NOT NULL REFERENCES department(dept_id),
    sla_hours        INTEGER NOT NULL CHECK (sla_hours > 0),
    default_priority TEXT NOT NULL CHECK (default_priority IN ('LOW','MEDIUM','HIGH'))
);

CREATE TABLE IF NOT EXISTS ward (
    ward_id INTEGER PRIMARY KEY,
    name    TEXT NOT NULL UNIQUE
);

-- Street gazetteer: stands in for the city GIS service in the prototype
CREATE TABLE IF NOT EXISTS street (
    street_id INTEGER PRIMARY KEY,
    name      TEXT NOT NULL UNIQUE,
    ward_id   INTEGER NOT NULL REFERENCES ward(ward_id),
    base_lat  REAL NOT NULL,
    base_lon  REAL NOT NULL
);

-- Stands in for the city Work Management System (WMS)
CREATE TABLE IF NOT EXISTS work_order (
    work_order_id INTEGER PRIMARY KEY,
    wo_number     TEXT UNIQUE,
    category_id   INTEGER NOT NULL REFERENCES category(category_id),
    dept_id       INTEGER NOT NULL REFERENCES department(dept_id),
    ward_id       INTEGER REFERENCES ward(ward_id),
    lat           REAL,
    lon           REAL,
    priority      TEXT NOT NULL CHECK (priority IN ('LOW','MEDIUM','HIGH','URGENT')),
    status        TEXT NOT NULL DEFAULT 'OPEN'
                  CHECK (status IN ('OPEN','ASSIGNED','IN_PROGRESS','COMPLETED')),
    report_count  INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL,
    due_at        TEXT NOT NULL,
    completed_at  TEXT
);

CREATE TABLE IF NOT EXISTS service_request (
    request_id         INTEGER PRIMARY KEY,
    ticket             TEXT UNIQUE,
    channel            TEXT NOT NULL CHECK (channel IN ('WEB','EMAIL','PHONE')),
    text_redacted      TEXT NOT NULL,
    address            TEXT,
    lat                REAL,
    lon                REAL,
    ward_id            INTEGER REFERENCES ward(ward_id),
    category_id        INTEGER REFERENCES category(category_id),
    confidence         REAL CHECK (confidence BETWEEN 0 AND 1),
    urgency            TEXT NOT NULL DEFAULT 'ROUTINE' CHECK (urgency IN ('ROUTINE','URGENT')),
    status             TEXT NOT NULL
                       CHECK (status IN ('NEEDS_REVIEW','ROUTED','DUPLICATE','CLOSED')),
    review_reason      TEXT,
    duplicate_of       INTEGER REFERENCES service_request(request_id),
    work_order_id      INTEGER REFERENCES work_order(work_order_id),
    contact            TEXT,
    classifier_backend TEXT,
    processed_ms       REAL,
    auto_routed        INTEGER NOT NULL DEFAULT 0 CHECK (auto_routed IN (0,1)),
    created_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_request_status ON service_request(status);
CREATE INDEX IF NOT EXISTS ix_request_cat ON service_request(category_id, created_at);

CREATE TABLE IF NOT EXISTS agent_review (
    review_id             INTEGER PRIMARY KEY,
    request_id            INTEGER NOT NULL REFERENCES service_request(request_id),
    predicted_category_id INTEGER REFERENCES category(category_id),
    final_category_id     INTEGER NOT NULL REFERENCES category(category_id),
    agent                 TEXT NOT NULL,
    reason                TEXT,
    resolved_at           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notification (
    notification_id INTEGER PRIMARY KEY,
    request_id      INTEGER NOT NULL REFERENCES service_request(request_id),
    channel         TEXT NOT NULL CHECK (channel IN ('EMAIL','SMS','NONE')),
    message         TEXT NOT NULL,
    sent_at         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS setting (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- ETL target: two years of cleaned historical requests used to train and test the classifier
CREATE TABLE IF NOT EXISTS historical_request (
    hist_id       INTEGER PRIMARY KEY,
    source_row    INTEGER NOT NULL,
    created_at    TEXT NOT NULL,
    channel       TEXT NOT NULL,
    text_redacted TEXT NOT NULL,
    category_id   INTEGER NOT NULL REFERENCES category(category_id),
    address       TEXT,
    lat           REAL,
    lon           REAL,
    ward_id       INTEGER REFERENCES ward(ward_id)
);
CREATE INDEX IF NOT EXISTS ix_hist_cat ON historical_request(category_id);

CREATE TABLE IF NOT EXISTS etl_run (
    run_id             INTEGER PRIMARY KEY,
    started_at         TEXT NOT NULL,
    source_file        TEXT NOT NULL,
    rows_extracted     INTEGER NOT NULL,
    rows_loaded        INTEGER NOT NULL,
    rows_rejected      INTEGER NOT NULL,
    duplicates_removed INTEGER NOT NULL,
    pii_redactions     INTEGER NOT NULL
);
