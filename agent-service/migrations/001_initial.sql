-- Agent SQLite schema v1

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS demo_sessions (
    session_id TEXT PRIMARY KEY,
    caller_id TEXT NOT NULL,
    allowed_patients_json TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    caller_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    patient_id TEXT NOT NULL,
    visit_context TEXT NOT NULL,
    as_of TEXT NOT NULL,
    run_status TEXT NOT NULL,
    profile_id TEXT,
    error_code TEXT,
    trace_id TEXT NOT NULL,
    usage_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (caller_id, request_id)
);

CREATE INDEX IF NOT EXISTS idx_runs_status ON runs (run_status);

CREATE TABLE IF NOT EXISTS profiles (
    profile_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    caller_id TEXT NOT NULL,
    patient_id TEXT NOT NULL,
    profile_version INTEGER NOT NULL,
    review_status TEXT NOT NULL,
    review_revision INTEGER NOT NULL,
    profile_json TEXT NOT NULL,
    sources_json TEXT NOT NULL,
    usage_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs (run_id)
);

CREATE INDEX IF NOT EXISTS idx_profiles_patient ON profiles (patient_id, caller_id);

CREATE TABLE IF NOT EXISTS audit_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor TEXT NOT NULL,
    run_id TEXT,
    profile_id TEXT,
    action TEXT NOT NULL,
    detail_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_snapshots (
    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    record_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    record_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (run_id, record_id)
);
