-- Agentes de organización. Mismas columnas que sqlite/0011_organization_agents.sql.
ALTER TABLE agents ADD COLUMN category text NOT NULL DEFAULT 'general';
ALTER TABLE agents ADD COLUMN base_agent text NOT NULL DEFAULT 'general';
ALTER TABLE agents ADD COLUMN tools jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE agents ADD COLUMN model text;
ALTER TABLE agents ADD COLUMN updated_at timestamptz;
CREATE INDEX idx_agents_org_status ON agents(organization_id, status);
