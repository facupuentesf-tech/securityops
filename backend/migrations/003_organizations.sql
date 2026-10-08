CREATE TABLE organizations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE CHECK (length(trim(name)) BETWEEN 1 AND 120),
    created_at TEXT NOT NULL
);

INSERT INTO organizations (id, name, created_at)
VALUES (1, 'Organización inicial', strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now'));

ALTER TABLE users
ADD COLUMN organization_id INTEGER REFERENCES organizations(id);

ALTER TABLE incidents
ADD COLUMN organization_id INTEGER REFERENCES organizations(id);

UPDATE users SET organization_id = 1;
UPDATE incidents SET organization_id = 1;

CREATE TRIGGER users_organization_required_insert
BEFORE INSERT ON users
WHEN NEW.organization_id IS NULL
BEGIN
    SELECT RAISE(ABORT, 'users.organization_id is required');
END;

CREATE TRIGGER users_organization_required_update
BEFORE UPDATE OF organization_id ON users
WHEN NEW.organization_id IS NULL
BEGIN
    SELECT RAISE(ABORT, 'users.organization_id is required');
END;

CREATE TRIGGER incidents_organization_required_insert
BEFORE INSERT ON incidents
WHEN NEW.organization_id IS NULL
BEGIN
    SELECT RAISE(ABORT, 'incidents.organization_id is required');
END;

CREATE TRIGGER incidents_organization_required_update
BEFORE UPDATE OF organization_id ON incidents
WHEN NEW.organization_id IS NULL
BEGIN
    SELECT RAISE(ABORT, 'incidents.organization_id is required');
END;

CREATE INDEX idx_users_organization ON users (organization_id, id);
CREATE INDEX idx_incidents_organization ON incidents (organization_id, id);
CREATE INDEX idx_incidents_organization_status ON incidents (organization_id, status, id);
CREATE INDEX idx_incidents_organization_severity ON incidents (organization_id, severity, id);
