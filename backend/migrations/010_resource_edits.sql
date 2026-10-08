-- Extend the action CHECK while preserving every event and the ID high-water mark.
CREATE TEMP TABLE audit_saved_sequence AS SELECT seq FROM sqlite_sequence WHERE name = 'audit_logs';

CREATE TABLE audit_logs_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id INTEGER NOT NULL REFERENCES organizations(id),
    actor_id INTEGER NOT NULL,
    actor_name TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('created', 'status_changed', 'note_created', 'linked', 'unlinked', 'assignee_changed', 'role_changed', 'deactivated', 'reactivated', 'password_reset', 'user_updated', 'updated')),
    resource_type TEXT NOT NULL CHECK (resource_type IN ('incident', 'asset', 'risk', 'control', 'user')),
    resource_id INTEGER NOT NULL CHECK (resource_id > 0),
    occurred_at TEXT NOT NULL,
    details TEXT NOT NULL CHECK (json_valid(details) AND json_type(details) = 'object')
);

INSERT INTO audit_logs_new SELECT * FROM audit_logs;
DROP TABLE audit_logs;
ALTER TABLE audit_logs_new RENAME TO audit_logs;
UPDATE sqlite_sequence SET seq = MAX(seq, COALESCE((SELECT seq FROM audit_saved_sequence), 0)) WHERE name = 'audit_logs';
DELETE FROM sqlite_sequence WHERE name = 'audit_logs'
    AND NOT EXISTS (SELECT 1 FROM audit_saved_sequence)
    AND NOT EXISTS (SELECT 1 FROM audit_logs);
DROP TABLE audit_saved_sequence;

CREATE INDEX idx_audit_organization_date ON audit_logs (organization_id, occurred_at DESC, id DESC);
CREATE INDEX idx_audit_organization_actor ON audit_logs (organization_id, actor_id, occurred_at DESC, id DESC);
