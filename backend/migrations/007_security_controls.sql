CREATE TABLE security_controls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id INTEGER NOT NULL REFERENCES organizations(id),
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    description TEXT,
    type TEXT NOT NULL CHECK (type IN ('preventive', 'detective', 'corrective')),
    status TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('planned', 'implemented', 'retired')),
    created_at TEXT NOT NULL
);

CREATE UNIQUE INDEX idx_controls_id_organization ON security_controls (id, organization_id);
CREATE UNIQUE INDEX idx_risks_id_organization ON risks (id, organization_id);
CREATE INDEX idx_controls_organization ON security_controls (organization_id, id);
CREATE INDEX idx_controls_organization_type ON security_controls (organization_id, type, id);
CREATE INDEX idx_controls_organization_status ON security_controls (organization_id, status, id);

CREATE TABLE risk_controls (
    risk_id INTEGER NOT NULL,
    control_id INTEGER NOT NULL,
    organization_id INTEGER NOT NULL REFERENCES organizations(id),
    PRIMARY KEY (risk_id, control_id),
    FOREIGN KEY (risk_id, organization_id) REFERENCES risks(id, organization_id),
    FOREIGN KEY (control_id, organization_id) REFERENCES security_controls(id, organization_id)
);
CREATE INDEX idx_risk_controls_control ON risk_controls (control_id, organization_id);
