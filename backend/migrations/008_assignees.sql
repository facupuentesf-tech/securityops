ALTER TABLE incidents ADD COLUMN assignee_id INTEGER REFERENCES users(id);
ALTER TABLE risks ADD COLUMN assignee_id INTEGER REFERENCES users(id);

CREATE INDEX idx_incidents_organization_assignee ON incidents (organization_id, assignee_id, id);
CREATE INDEX idx_risks_organization_assignee ON risks (organization_id, assignee_id, id);

CREATE TRIGGER incidents_assignee_insert
BEFORE INSERT ON incidents
WHEN NEW.assignee_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM users WHERE id = NEW.assignee_id AND organization_id = NEW.organization_id
    AND is_active = 1 AND role IN ('administrador', 'analista')
)
BEGIN
    SELECT RAISE(ABORT, 'Incident assignee must be eligible and in the same organization');
END;

CREATE TRIGGER incidents_assignee_update
BEFORE UPDATE OF assignee_id, organization_id ON incidents
WHEN NEW.assignee_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM users WHERE id = NEW.assignee_id AND organization_id = NEW.organization_id
    AND is_active = 1 AND role IN ('administrador', 'analista')
)
BEGIN
    SELECT RAISE(ABORT, 'Incident assignee must be eligible and in the same organization');
END;

CREATE TRIGGER risks_assignee_insert
BEFORE INSERT ON risks
WHEN NEW.assignee_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM users WHERE id = NEW.assignee_id AND organization_id = NEW.organization_id
    AND is_active = 1 AND role IN ('administrador', 'analista')
)
BEGIN
    SELECT RAISE(ABORT, 'Risk assignee must be eligible and in the same organization');
END;

CREATE TRIGGER risks_assignee_update
BEFORE UPDATE OF assignee_id, organization_id ON risks
WHEN NEW.assignee_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM users WHERE id = NEW.assignee_id AND organization_id = NEW.organization_id
    AND is_active = 1 AND role IN ('administrador', 'analista')
)
BEGIN
    SELECT RAISE(ABORT, 'Risk assignee must be eligible and in the same organization');
END;

CREATE TRIGGER users_assignee_organization_update
BEFORE UPDATE OF organization_id ON users
WHEN EXISTS (SELECT 1 FROM incidents WHERE assignee_id = OLD.id AND organization_id IS NOT NEW.organization_id)
  OR EXISTS (SELECT 1 FROM risks WHERE assignee_id = OLD.id AND organization_id IS NOT NEW.organization_id)
BEGIN
    SELECT RAISE(ABORT, 'Cannot move an assigned user to another organization');
END;

CREATE TRIGGER users_clear_ineligible_assignments
AFTER UPDATE OF is_active, role ON users
WHEN NEW.is_active = 0 OR NEW.role = 'lector'
BEGIN
    UPDATE incidents SET assignee_id = NULL WHERE assignee_id = NEW.id AND organization_id = NEW.organization_id;
    UPDATE risks SET assignee_id = NULL WHERE assignee_id = NEW.id AND organization_id = NEW.organization_id;
END;
