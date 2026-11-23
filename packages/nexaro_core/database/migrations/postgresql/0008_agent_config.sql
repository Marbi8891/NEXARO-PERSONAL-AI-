-- Configuración persistente para agentes personalizados. No concede herramientas ejecutables.
ALTER TABLE agents ADD COLUMN category text NOT NULL DEFAULT 'custom';
ALTER TABLE agents ADD COLUMN model text;
ALTER TABLE agents ADD COLUMN tools_json text NOT NULL DEFAULT '[]';
ALTER TABLE agents ADD COLUMN permissions_json text NOT NULL DEFAULT '{}';
ALTER TABLE agents ADD COLUMN memory_json text NOT NULL DEFAULT '{"enabled":false,"scope":"none"}';
ALTER TABLE agents ADD COLUMN autonomy text NOT NULL DEFAULT 'assisted' CHECK (autonomy IN ('assisted','supervised','autonomous'));
ALTER TABLE agents ADD COLUMN template_id text;
ALTER TABLE agents ADD COLUMN updated_at timestamptz;
