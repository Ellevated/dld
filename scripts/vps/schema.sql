-- scripts/vps/schema.sql
-- Orchestrator runtime state (SQLite WAL mode)
-- Usage: sqlite3 orchestrator.db < schema.sql

PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 5000;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS project_state (
    project_id   TEXT PRIMARY KEY,
    path         TEXT NOT NULL,
    chat_id      INTEGER,
    topic_id     INTEGER,
    provider     TEXT NOT NULL DEFAULT 'claude',
    phase        TEXT NOT NULL DEFAULT 'idle',
    current_task TEXT,
    auto_approve_timeout INTEGER NOT NULL DEFAULT 30,
    enabled      INTEGER NOT NULL DEFAULT 1,
    updated_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_project_state_chat_topic_unique
ON project_state(chat_id, topic_id)
WHERE topic_id IS NOT NULL;

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
    branch       TEXT,
    started_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    finished_at  TEXT,
    exit_code    INTEGER,
    output_summary TEXT
);

-- Seed slots: 2 for claude, 1 for codex, 1 for gemini
INSERT OR IGNORE INTO compute_slots (slot_number, provider) VALUES (1, 'claude');
INSERT OR IGNORE INTO compute_slots (slot_number, provider) VALUES (2, 'claude');
INSERT OR IGNORE INTO compute_slots (slot_number, provider) VALUES (3, 'codex');
INSERT OR IGNORE INTO compute_slots (slot_number, provider) VALUES (4, 'gemini');

-- Finding deduplication store (Phase 2)
CREATE TABLE IF NOT EXISTS night_findings (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id   TEXT NOT NULL REFERENCES project_state(project_id),
    fingerprint  TEXT NOT NULL,
    severity     TEXT NOT NULL DEFAULT 'medium',
    confidence   TEXT NOT NULL DEFAULT 'medium',
    file_path    TEXT,
    line_range   TEXT,
    summary      TEXT NOT NULL,
    suggestion   TEXT,
    status       TEXT NOT NULL DEFAULT 'new',
    message_id   INTEGER,
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    reviewed_at  TEXT,
    UNIQUE(project_id, fingerprint)
);
