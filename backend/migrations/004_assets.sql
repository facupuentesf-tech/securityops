CREATE TABLE assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id INTEGER NOT NULL REFERENCES organizations(id),
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    type TEXT NOT NULL CHECK (type IN ('hardware', 'software', 'service', 'data')),
    description TEXT,
    criticality TEXT NOT NULL CHECK (criticality IN ('low', 'medium', 'high', 'critical')),
    created_at TEXT NOT NULL
);

CREATE INDEX idx_assets_organization ON assets (organization_id, id);
CREATE INDEX idx_assets_organization_type ON assets (organization_id, type, id);
CREATE INDEX idx_assets_organization_criticality ON assets (organization_id, criticality, id);
