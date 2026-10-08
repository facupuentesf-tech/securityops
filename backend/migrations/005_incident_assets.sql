CREATE UNIQUE INDEX idx_incidents_id_organization ON incidents (id, organization_id);
CREATE UNIQUE INDEX idx_assets_id_organization ON assets (id, organization_id);

CREATE TABLE incident_assets (
    incident_id INTEGER NOT NULL,
    asset_id INTEGER NOT NULL,
    organization_id INTEGER NOT NULL REFERENCES organizations(id),
    PRIMARY KEY (incident_id, asset_id),
    FOREIGN KEY (incident_id, organization_id) REFERENCES incidents(id, organization_id),
    FOREIGN KEY (asset_id, organization_id) REFERENCES assets(id, organization_id)
);
CREATE INDEX idx_incident_assets_asset ON incident_assets (asset_id, organization_id);
