-- Agentes personales por usuario. Mismas columnas que sqlite/0010_user_agents.sql.
CREATE TABLE user_agents (
    id uuid PRIMARY KEY,
    owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name text NOT NULL CHECK (length(name) BETWEEN 1 AND 80),
    description text NOT NULL DEFAULT '',
    category text NOT NULL DEFAULT 'general',
    base_agent text NOT NULL DEFAULT 'general',
    instructions text NOT NULL DEFAULT '',
    tools jsonb NOT NULL DEFAULT '[]'::jsonb,
    model text,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (owner_user_id, name)
);
CREATE INDEX idx_user_agents_owner ON user_agents(owner_user_id, status);
