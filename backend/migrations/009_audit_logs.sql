CREATE TABLE audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id INTEGER NOT NULL REFERENCES organizations(id),
    actor_id INTEGER NOT NULL,
    actor_name TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('created', 'status_changed', 'note_created', 'linked', 'unlinked', 'assignee_changed', 'role_changed', 'deactivated', 'reactivated', 'password_reset', 'user_updated')),
    resource_type TEXT NOT NULL CHECK (resource_type IN ('incident', 'asset', 'risk', 'control', 'user')),
    resource_id INTEGER NOT NULL CHECK (resource_id > 0),
    occurred_at TEXT NOT NULL,
    details TEXT NOT NULL CHECK (json_valid(details) AND json_type(details) = 'object')
);

CREATE INDEX idx_audit_organization_date ON audit_logs (organization_id, occurred_at DESC, id DESC);
CREATE INDEX idx_audit_organization_actor ON audit_logs (organization_id, actor_id, occurred_at DESC, id DESC);
