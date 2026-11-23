-- Configuración persistente para agentes personalizados. No concede herramientas ejecutables.
ALTER TABLE agents ADD COLUMN category TEXT NOT NULL DEFAULT 'custom';
ALTER TABLE agents ADD COLUMN model TEXT;
ALTER TABLE agents ADD COLUMN tools_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE agents ADD COLUMN permissions_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE agents ADD COLUMN memory_json TEXT NOT NULL DEFAULT '{"enabled":false,"scope":"none"}';
ALTER TABLE agents ADD COLUMN autonomy TEXT NOT NULL DEFAULT 'assisted' CHECK (autonomy IN ('assisted','supervised','autonomous'));
ALTER TABLE agents ADD COLUMN template_id TEXT;
ALTER TABLE agents ADD COLUMN updated_at TIMESTAMP;
