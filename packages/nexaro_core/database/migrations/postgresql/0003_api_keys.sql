-- Claves de API por organización (ADR-0009). Mismas tablas y columnas que sqlite/0003_api_keys.sql.
-- Sin RLS a propósito: la clave se busca por su hash antes de conocer la organización.

CREATE TABLE api_keys (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name text NOT NULL CHECK (length(name) BETWEEN 1 AND 80),
    prefix text NOT NULL,
    key_hash text NOT NULL UNIQUE,
    created_by uuid NOT NULL REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz,
    last_used_at timestamptz,
    revoked_at timestamptz,
    UNIQUE (id, organization_id)
);
CREATE INDEX idx_api_keys_org ON api_keys(organization_id, created_at);

ALTER TABLE model_usage ADD COLUMN api_key_id uuid;
ALTER TABLE model_usage ADD FOREIGN KEY (api_key_id, organization_id) REFERENCES api_keys(id, organization_id);
CREATE INDEX idx_model_usage_org ON model_usage(organization_id, created_at);

INSERT INTO permissions (id, description) VALUES
    ('api_keys:manage', 'Crear, listar y revocar claves de API');
INSERT INTO role_permissions (role_id, permission_id) VALUES
    ('owner', 'api_keys:manage'),
    ('admin', 'api_keys:manage');
