CREATE UNIQUE INDEX idx_users_id_organization ON users (id, organization_id);

CREATE TABLE risk_assessments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id INTEGER NOT NULL REFERENCES organizations(id),
    risk_id INTEGER NOT NULL,
    evaluator_id INTEGER NOT NULL,
    evaluator_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    residual_probability INTEGER NOT NULL CHECK (typeof(residual_probability) = 'integer' AND residual_probability BETWEEN 1 AND 5),
    residual_impact INTEGER NOT NULL CHECK (typeof(residual_impact) = 'integer' AND residual_impact BETWEEN 1 AND 5),
    justification TEXT NOT NULL CHECK (length(trim(justification)) BETWEEN 1 AND 5000 AND justification = trim(justification)),
    original_probability INTEGER NOT NULL CHECK (typeof(original_probability) = 'integer' AND original_probability BETWEEN 1 AND 5),
    original_impact INTEGER NOT NULL CHECK (typeof(original_impact) = 'integer' AND original_impact BETWEEN 1 AND 5),
    original_score INTEGER NOT NULL CHECK (typeof(original_score) = 'integer' AND original_score = original_probability * original_impact),
    FOREIGN KEY (risk_id, organization_id) REFERENCES risks (id, organization_id),
    FOREIGN KEY (evaluator_id, organization_id) REFERENCES users (id, organization_id)
);
CREATE INDEX idx_assessments_risk_date ON risk_assessments (organization_id, risk_id, created_at DESC, id DESC);

-- Extend the action CHECK while preserving every event and the ID high-water mark.
CREATE TEMP TABLE audit_saved_sequence AS SELECT seq FROM sqlite_sequence WHERE name = 'audit_logs';

CREATE TABLE audit_logs_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id INTEGER NOT NULL REFERENCES organizations(id),
    actor_id INTEGER NOT NULL,
    actor_name TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('created', 'status_changed', 'note_created', 'linked', 'unlinked', 'assignee_changed', 'role_changed', 'deactivated', 'reactivated', 'password_reset', 'user_updated', 'updated', 'assessed')),
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
