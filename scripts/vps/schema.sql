-- scripts/vps/schema.sql
-- Orchestrator runtime state (SQLite WAL mode)
-- Usage: sqlite3 orchestrator.db < schema.sql

PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 5000;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS project_state (
    project_id   TEXT PRIMARY KEY,
    path         TEXT NOT NULL,
    topic_id     INTEGER,
    provider     TEXT NOT NULL DEFAULT 'claude',
    phase        TEXT NOT NULL DEFAULT 'idle',
    current_task TEXT,
    auto_approve_timeout INTEGER NOT NULL DEFAULT 30,
    enabled      INTEGER NOT NULL DEFAULT 1,
    updated_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS compute_slots (
    slot_number  INTEGER PRIMARY KEY,
    provider     TEXT NOT NULL,
    project_id   TEXT REFERENCES project_state(project_id),
    pid          INTEGER,
    pueue_id     INTEGER,
    acquired_at  TEXT
);

CREATE TABLE IF NOT EXISTS task_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id   TEXT NOT NULL REFERENCES project_state(project_id),
    task_label   TEXT NOT NULL,
    skill        TEXT NOT NULL DEFAULT 'autopilot',
    status       TEXT NOT NULL DEFAULT 'queued',
    pueue_id     INTEGER,
    started_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    finished_at  TEXT,
    exit_code    INTEGER,
    output_summary TEXT
);

-- Seed slots: 2 for claude, 1 for codex
INSERT OR IGNORE INTO compute_slots (slot_number, provider) VALUES (1, 'claude');
INSERT OR IGNORE INTO compute_slots (slot_number, provider) VALUES (2, 'claude');
INSERT OR IGNORE INTO compute_slots (slot_number, provider) VALUES (3, 'codex');
