CREATE TABLE IF NOT EXISTS incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL CHECK (length(trim(title)) > 0),
    description TEXT NOT NULL CHECK (length(trim(description)) > 0),
    severity TEXT NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    status TEXT NOT NULL CHECK (status IN ('open', 'investigating', 'resolved')),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS incident_status_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id INTEGER NOT NULL REFERENCES incidents(id),
    previous_status TEXT NOT NULL CHECK (previous_status IN ('open', 'investigating', 'resolved')),
    new_status TEXT NOT NULL CHECK (new_status IN ('open', 'investigating', 'resolved')),
    changed_at TEXT NOT NULL,
    CHECK (previous_status <> new_status)
);

CREATE INDEX IF NOT EXISTS idx_incident_history
ON incident_status_history (incident_id, id);

CREATE TABLE IF NOT EXISTS incident_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id INTEGER NOT NULL REFERENCES incidents(id),
    content TEXT NOT NULL CHECK (length(content) BETWEEN 1 AND 5000),
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_incident_notes
ON incident_notes (incident_id, created_at, id);
