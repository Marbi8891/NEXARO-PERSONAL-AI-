-- Biblioteca de prompts por organización (ADR-0024). Ver postgresql/0011_prompt_library.sql.
-- tags y variables se guardan como JSON en texto; version empieza en 1 y crece con cada cambio.

CREATE TABLE prompts (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name TEXT NOT NULL CHECK (length(name) BETWEEN 2 AND 120),
    description TEXT NOT NULL DEFAULT '' CHECK (length(description) <= 1000),
    category TEXT NOT NULL CHECK (length(category) BETWEEN 1 AND 80),
    tags TEXT NOT NULL DEFAULT '[]',
    system_prompt TEXT NOT NULL DEFAULT '' CHECK (length(system_prompt) <= 20000),
    user_template TEXT NOT NULL CHECK (length(user_template) BETWEEN 1 AND 20000),
    variables TEXT NOT NULL DEFAULT '[]',
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    catalogue_id TEXT CHECK (catalogue_id IS NULL OR length(catalogue_id) <= 80),
    created_by TEXT REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP,
    UNIQUE (id, organization_id)
);
CREATE INDEX idx_prompts_org ON prompts(organization_id, updated_at);

CREATE TABLE prompt_versions (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    prompt_id TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 1),
    snapshot TEXT NOT NULL,
    changelog TEXT NOT NULL DEFAULT '' CHECK (length(changelog) <= 200),
    created_by TEXT REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (prompt_id, version),
    FOREIGN KEY (prompt_id, organization_id)
        REFERENCES prompts(id, organization_id) ON DELETE CASCADE
);

INSERT INTO permissions (id, description) VALUES
    ('prompts:read', 'Ver la biblioteca de prompts'),
    ('prompts:write', 'Crear, editar y borrar prompts');
INSERT INTO role_permissions (role_id, permission_id) VALUES
    ('owner', 'prompts:read'),
    ('owner', 'prompts:write'),
    ('admin', 'prompts:read'),
    ('admin', 'prompts:write'),
    ('member', 'prompts:read'),
    ('member', 'prompts:write'),
    ('viewer', 'prompts:read');
