-- Plataforma multiorganización (ADR-0005). Mismas tablas y columnas que sqlite/0002_platform.sql.

CREATE TABLE organizations (
    id uuid PRIMARY KEY,
    name text NOT NULL CHECK (length(name) BETWEEN 1 AND 120),
    slug text NOT NULL UNIQUE CHECK (length(slug) BETWEEN 2 AND 63),
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended')),
    created_by uuid REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE roles (
    id text PRIMARY KEY,
    description text NOT NULL
);

CREATE TABLE permissions (
    id text PRIMARY KEY,
    description text NOT NULL
);

CREATE TABLE role_permissions (
    role_id text NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_id text NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE memberships (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES users(id),
    role_id text NOT NULL REFERENCES roles(id),
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended')),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, user_id)
);
CREATE INDEX idx_memberships_user ON memberships(user_id);

CREATE TABLE subscriptions (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL UNIQUE REFERENCES organizations(id) ON DELETE CASCADE,
    plan text NOT NULL DEFAULT 'free',
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'past_due', 'canceled')),
    current_period_end timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, organization_id)
);

CREATE TABLE model_providers (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    provider text NOT NULL CHECK (provider IN ('ollama', 'bedrock', 'sagemaker')),
    model text NOT NULL,
    enabled boolean NOT NULL DEFAULT true,
    config_json jsonb NOT NULL DEFAULT '{}',  -- nunca secretos: las credenciales vienen del rol de AWS
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, provider, model),
    UNIQUE (id, organization_id)
);

CREATE TABLE documents (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    title text NOT NULL,
    source text,
    mime_type text,
    size_bytes bigint CHECK (size_bytes IS NULL OR size_bytes >= 0),
    sha256 text,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processed', 'failed')),
    created_by uuid REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz,
    UNIQUE (id, organization_id)
);
CREATE INDEX idx_documents_org ON documents(organization_id, created_at);

CREATE TABLE document_chunks (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL,
    document_id uuid NOT NULL,
    ordinal integer NOT NULL CHECK (ordinal >= 0),
    content text NOT NULL,
    token_count integer,
    UNIQUE (document_id, ordinal),
    UNIQUE (id, organization_id),
    FOREIGN KEY (document_id, organization_id)
        REFERENCES documents(id, organization_id) ON DELETE CASCADE
);

CREATE TABLE embeddings (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL,
    chunk_id uuid NOT NULL,
    model text NOT NULL,
    dimensions integer NOT NULL CHECK (dimensions > 0),
    vector bytea NOT NULL,  -- pgvector sería lo natural; UNKNOWN si estará disponible (ADR-0005)
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (chunk_id, model),
    FOREIGN KEY (chunk_id, organization_id)
        REFERENCES document_chunks(id, organization_id) ON DELETE CASCADE
);
CREATE INDEX idx_embeddings_org ON embeddings(organization_id);

CREATE TABLE agents (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name text NOT NULL,
    description text,
    system_prompt text NOT NULL DEFAULT '',
    model_provider_id uuid,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
    created_by uuid REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, name),
    UNIQUE (id, organization_id),
    FOREIGN KEY (model_provider_id, organization_id)
        REFERENCES model_providers(id, organization_id)
);

CREATE TABLE agent_runs (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL,
    agent_id uuid NOT NULL,
    triggered_by uuid REFERENCES users(id),
    status text NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'canceled')),
    error_kind text,
    started_at timestamptz,
    finished_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, organization_id),
    FOREIGN KEY (agent_id, organization_id)
        REFERENCES agents(id, organization_id) ON DELETE CASCADE
);
CREATE INDEX idx_agent_runs_org ON agent_runs(organization_id, agent_id, created_at);

CREATE TABLE tasks (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    agent_run_id uuid,
    title text NOT NULL,
    status text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'in_progress', 'done', 'canceled')),
    due_at timestamptz,
    assignee_user_id uuid REFERENCES users(id),
    created_by uuid REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, organization_id),
    FOREIGN KEY (agent_run_id, organization_id) REFERENCES agent_runs(id, organization_id)
);
CREATE INDEX idx_tasks_org ON tasks(organization_id, status);

ALTER TABLE conversations ADD COLUMN organization_id uuid REFERENCES organizations(id);
ALTER TABLE model_usage ADD COLUMN organization_id uuid REFERENCES organizations(id);

INSERT INTO roles (id, description) VALUES
    ('owner', 'Control total, incluida la facturación'),
    ('admin', 'Gestiona miembros, modelos, agentes y datos'),
    ('member', 'Trabaja con documentos, agentes y tareas'),
    ('viewer', 'Solo lectura');

INSERT INTO permissions (id, description) VALUES
    ('org:read', 'Ver la organización'),
    ('org:manage', 'Editar la organización'),
    ('members:read', 'Ver miembros'),
    ('members:manage', 'Añadir, cambiar o quitar miembros'),
    ('documents:read', 'Leer documentos'),
    ('documents:write', 'Crear y borrar documentos'),
    ('agents:read', 'Ver agentes y ejecuciones'),
    ('agents:run', 'Ejecutar agentes'),
    ('agents:manage', 'Crear y editar agentes'),
    ('tasks:read', 'Ver tareas'),
    ('tasks:write', 'Crear y editar tareas'),
    ('models:manage', 'Configurar proveedores de modelos'),
    ('usage:read', 'Ver uso y costes'),
    ('billing:manage', 'Gestionar la suscripción'),
    ('audit:read', 'Ver la auditoría');

INSERT INTO role_permissions (role_id, permission_id) SELECT 'owner', id FROM permissions;
INSERT INTO role_permissions (role_id, permission_id)
    SELECT 'admin', id FROM permissions WHERE id <> 'billing:manage';
INSERT INTO role_permissions (role_id, permission_id)
    SELECT 'member', id FROM permissions WHERE id IN (
        'org:read', 'members:read', 'documents:read', 'documents:write', 'agents:read',
        'agents:run', 'tasks:read', 'tasks:write');
INSERT INTO role_permissions (role_id, permission_id)
    SELECT 'viewer', id FROM permissions WHERE id IN (
        'org:read', 'members:read', 'documents:read', 'agents:read', 'tasks:read');

-- Row Level Security: segunda barrera de aislamiento. Sin `nexaro.organization_id` no se ve
-- ninguna fila. No afecta a superusuarios: la aplicación debe conectar con un rol sin privilegios.
DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'documents', 'document_chunks', 'embeddings', 'agents', 'agent_runs',
        'tasks', 'model_providers', 'subscriptions'
    ] LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
        EXECUTE format(
            'CREATE POLICY tenant_isolation ON %I
                 USING (organization_id = nullif(current_setting(''nexaro.organization_id'', true), '''')::uuid)
                 WITH CHECK (organization_id = nullif(current_setting(''nexaro.organization_id'', true), '''')::uuid)',
            t);
    END LOOP;
END $$;
