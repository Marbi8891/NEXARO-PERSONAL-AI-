-- Claves de API por organización (ADR-0009). Ver postgresql/0003_api_keys.sql: mismas tablas y columnas.
-- Solo se guarda el hash SHA-256 de la clave (256 bits de entropía: no hace falta un hash lento).

CREATE TABLE api_keys (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 80),
    prefix TEXT NOT NULL,
    key_hash TEXT NOT NULL UNIQUE,
    created_by TEXT NOT NULL REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    last_used_at TIMESTAMP,
    revoked_at TIMESTAMP,
    UNIQUE (id, organization_id)
);
CREATE INDEX idx_api_keys_org ON api_keys(organization_id, created_at);

-- SQLite no permite añadir una clave foránea compuesta con ALTER TABLE y no se reconstruye
-- model_usage con datos reales: la coherencia (id, organization_id) la impone este trigger.
-- En PostgreSQL es una clave foránea compuesta.
ALTER TABLE model_usage ADD COLUMN api_key_id TEXT;
CREATE TRIGGER model_usage_api_key_same_org BEFORE INSERT ON model_usage
WHEN NEW.api_key_id IS NOT NULL
 AND NOT EXISTS (SELECT 1 FROM api_keys WHERE id = NEW.api_key_id AND organization_id IS NEW.organization_id)
BEGIN
    SELECT RAISE(ABORT, 'api_key_id no pertenece a organization_id');
END;
CREATE INDEX idx_model_usage_org ON model_usage(organization_id, created_at);

INSERT INTO permissions (id, description) VALUES
    ('api_keys:manage', 'Crear, listar y revocar claves de API');
INSERT INTO role_permissions (role_id, permission_id) VALUES
    ('owner', 'api_keys:manage'),
    ('admin', 'api_keys:manage');
