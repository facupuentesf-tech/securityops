CREATE TABLE risks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id INTEGER NOT NULL REFERENCES organizations(id),
    title TEXT NOT NULL CHECK (length(trim(title)) > 0),
    description TEXT,
    probability INTEGER NOT NULL CHECK (typeof(probability) = 'integer' AND probability BETWEEN 1 AND 5),
    impact INTEGER NOT NULL CHECK (typeof(impact) = 'integer' AND impact BETWEEN 1 AND 5),
    status TEXT NOT NULL DEFAULT 'identified' CHECK (status IN ('identified', 'treating', 'accepted')),
    asset_id INTEGER,
    created_at TEXT NOT NULL,
    FOREIGN KEY (asset_id, organization_id) REFERENCES assets(id, organization_id)
);

CREATE INDEX idx_risks_organization ON risks (organization_id, id);
CREATE INDEX idx_risks_organization_status ON risks (organization_id, status, id);
CREATE INDEX idx_risks_organization_asset ON risks (organization_id, asset_id, id);
