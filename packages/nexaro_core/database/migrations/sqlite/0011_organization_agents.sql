-- Agentes de organización (ADR-0024): la tabla `agents` de 0002 ya existía para esto y no se
-- usaba. Se le añaden las columnas de los agentes personales (0010) para que ambos funcionen
-- igual. Solo se añaden columnas: no se borra ni se reescribe nada. `system_prompt` guarda las
-- instrucciones. `updated_at` sin DEFAULT: SQLite no admite CURRENT_TIMESTAMP en ADD COLUMN.
ALTER TABLE agents ADD COLUMN category TEXT NOT NULL DEFAULT 'general';
ALTER TABLE agents ADD COLUMN base_agent TEXT NOT NULL DEFAULT 'general';
ALTER TABLE agents ADD COLUMN tools TEXT NOT NULL DEFAULT '[]';
ALTER TABLE agents ADD COLUMN model TEXT;
ALTER TABLE agents ADD COLUMN updated_at TIMESTAMP;
CREATE INDEX idx_agents_org_status ON agents(organization_id, status);
