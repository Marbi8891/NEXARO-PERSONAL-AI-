-- Biblioteca de prompts por organización (ADR-0024). Mismas tablas y columnas que sqlite/0011_prompt_library.sql.

CREATE TABLE prompts (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name text NOT NULL CHECK (length(name) BETWEEN 2 AND 120),
    description text NOT NULL DEFAULT '' CHECK (length(description) <= 1000),
    category text NOT NULL CHECK (length(category) BETWEEN 1 AND 80),
    tags jsonb NOT NULL DEFAULT '[]',
    system_prompt text NOT NULL DEFAULT '' CHECK (length(system_prompt) <= 20000),
    user_template text NOT NULL CHECK (length(user_template) BETWEEN 1 AND 20000),
    variables jsonb NOT NULL DEFAULT '[]',
    version integer NOT NULL DEFAULT 1 CHECK (version >= 1),
    catalogue_id text CHECK (catalogue_id IS NULL OR length(catalogue_id) <= 80),
    created_by uuid REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz,
    UNIQUE (id, organization_id)
);
CREATE INDEX idx_prompts_org ON prompts(organization_id, updated_at);

CREATE TABLE prompt_versions (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL,
    prompt_id uuid NOT NULL,
    version integer NOT NULL CHECK (version >= 1),
    snapshot jsonb NOT NULL,
    changelog text NOT NULL DEFAULT '' CHECK (length(changelog) <= 200),
    created_by uuid REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
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

DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['prompts', 'prompt_versions'] LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
        EXECUTE format(
            'CREATE POLICY tenant_isolation ON %I
                USING (organization_id = nullif(current_setting(''nexaro.organization_id'', true), '''')::uuid)
                WITH CHECK (organization_id = nullif(current_setting(''nexaro.organization_id'', true), '''')::uuid)',
            t);
    END LOOP;
END $$;
