CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    display_name TEXT NOT NULL CHECK (length(trim(display_name)) > 0),
    email TEXT NOT NULL COLLATE NOCASE UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('administrador', 'analista', 'lector')),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL
);

CREATE TABLE sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    csrf_token TEXT NOT NULL,
    expires_at INTEGER NOT NULL
);

CREATE INDEX idx_sessions_expiry ON sessions (expires_at);

ALTER TABLE incident_status_history
ADD COLUMN changed_by INTEGER REFERENCES users(id);

ALTER TABLE incident_notes
ADD COLUMN created_by INTEGER REFERENCES users(id);
