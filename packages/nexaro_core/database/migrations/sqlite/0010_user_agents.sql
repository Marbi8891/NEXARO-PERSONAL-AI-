-- Agentes personales creados por cada usuario. Ver postgresql/0010_user_agents.sql.
-- Parten de un agente predefinido (`base_agent`): heredan sus reglas y, como máximo, sus
-- herramientas. `tools` es una lista JSON; `model` NULL = automático.
CREATE TABLE user_agents (
    id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 80),
    description TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'general',
    base_agent TEXT NOT NULL DEFAULT 'general',
    instructions TEXT NOT NULL DEFAULT '',
    tools TEXT NOT NULL DEFAULT '[]',
    model TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (owner_user_id, name)
);
CREATE INDEX idx_user_agents_owner ON user_agents(owner_user_id, status);
