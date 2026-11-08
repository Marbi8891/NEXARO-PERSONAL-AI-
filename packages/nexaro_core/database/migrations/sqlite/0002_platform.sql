-- Plataforma multiorganización (ADR-0005). Ver postgresql/0002_platform.sql: mismas tablas y columnas.

CREATE TABLE organizations (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 120),
    slug TEXT NOT NULL UNIQUE CHECK (length(slug) BETWEEN 2 AND 63),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended')),
    created_by TEXT REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE roles (
    id TEXT PRIMARY KEY,
    description TEXT NOT NULL
);

CREATE TABLE permissions (
    id TEXT PRIMARY KEY,
    description TEXT NOT NULL
);

CREATE TABLE role_permissions (
    role_id TEXT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_id TEXT NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE memberships (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id),
    role_id TEXT NOT NULL REFERENCES roles(id),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (organization_id, user_id)
);
CREATE INDEX idx_memberships_user ON memberships(user_id);

CREATE TABLE subscriptions (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL UNIQUE REFERENCES organizations(id) ON DELETE CASCADE,
    plan TEXT NOT NULL DEFAULT 'free',
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'past_due', 'canceled')),
    current_period_end TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (id, organization_id)
);

CREATE TABLE model_providers (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    provider TEXT NOT NULL CHECK (provider IN ('ollama', 'bedrock', 'sagemaker')),
    model TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    config_json TEXT NOT NULL DEFAULT '{}',  -- nunca secretos: las credenciales vienen del rol de AWS
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (organization_id, provider, model),
    UNIQUE (id, organization_id)
);

CREATE TABLE documents (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    source TEXT,
    mime_type TEXT,
    size_bytes INTEGER CHECK (size_bytes IS NULL OR size_bytes >= 0),
    sha256 TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processed', 'failed')),
    created_by TEXT REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP,
    UNIQUE (id, organization_id)
);
CREATE INDEX idx_documents_org ON documents(organization_id, created_at);

CREATE TABLE document_chunks (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    content TEXT NOT NULL,
    token_count INTEGER,
    UNIQUE (document_id, ordinal),
    UNIQUE (id, organization_id),
    FOREIGN KEY (document_id, organization_id)
        REFERENCES documents(id, organization_id) ON DELETE CASCADE
);

CREATE TABLE embeddings (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    chunk_id TEXT NOT NULL,
    model TEXT NOT NULL,
    dimensions INTEGER NOT NULL CHECK (dimensions > 0),
    vector BLOB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (chunk_id, model),
    FOREIGN KEY (chunk_id, organization_id)
        REFERENCES document_chunks(id, organization_id) ON DELETE CASCADE
);
CREATE INDEX idx_embeddings_org ON embeddings(organization_id);

CREATE TABLE agents (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    system_prompt TEXT NOT NULL DEFAULT '',
    model_provider_id TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
    created_by TEXT REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (organization_id, name),
    UNIQUE (id, organization_id),
    FOREIGN KEY (model_provider_id, organization_id)
        REFERENCES model_providers(id, organization_id)
);

CREATE TABLE agent_runs (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    triggered_by TEXT REFERENCES users(id),
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'canceled')),
    error_kind TEXT,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (id, organization_id),
    FOREIGN KEY (agent_id, organization_id)
        REFERENCES agents(id, organization_id) ON DELETE CASCADE
);
CREATE INDEX idx_agent_runs_org ON agent_runs(organization_id, agent_id, created_at);

CREATE TABLE tasks (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    agent_run_id TEXT,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'in_progress', 'done', 'canceled')),
    due_at TIMESTAMP,
    assignee_user_id TEXT REFERENCES users(id),
    created_by TEXT REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (id, organization_id),
    FOREIGN KEY (agent_run_id, organization_id) REFERENCES agent_runs(id, organization_id)
);
CREATE INDEX idx_tasks_org ON tasks(organization_id, status);

ALTER TABLE conversations ADD COLUMN organization_id TEXT REFERENCES organizations(id);
ALTER TABLE model_usage ADD COLUMN organization_id TEXT REFERENCES organizations(id);

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
