-- Línea base PostgreSQL: equivale al esquema que SQLite construye en la migración 1.
-- La aplicación aún no ejecuta sobre PostgreSQL (ADR-0005); este DDL se valida en los tests.

CREATE TABLE users (
    id uuid PRIMARY KEY,
    email text NOT NULL,
    password_hash text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    role text NOT NULL DEFAULT 'user' CHECK (role IN ('admin', 'user')),
    is_active boolean NOT NULL DEFAULT true,
    approval_status text NOT NULL DEFAULT 'approved'
        CHECK (approval_status IN ('pending', 'approved', 'rejected'))
);
CREATE UNIQUE INDEX users_email_lower ON users (lower(email));

CREATE TABLE sessions (
    id uuid PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES users(id),
    token_hash text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz
);
CREATE INDEX idx_sessions_user_id ON sessions(user_id);

CREATE TABLE app_settings (
    key text PRIMARY KEY,
    value text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO app_settings (key, value) VALUES ('public_registration_enabled', '0');

CREATE TABLE conversations (
    id text PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),
    user_id uuid REFERENCES users(id)
);
CREATE INDEX idx_conversations_user_id ON conversations(user_id);

CREATE TABLE messages (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    conversation_id text NOT NULL REFERENCES conversations(id),
    role text NOT NULL,
    content text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_messages_conversation_id ON messages(conversation_id, id);

CREATE TABLE audit_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    occurred_at timestamptz NOT NULL,
    actor_user_id text,
    action text NOT NULL,
    outcome text NOT NULL CHECK (outcome IN ('success', 'failure', 'denied')),
    target_type text,
    target_id text,
    ip text,
    details jsonb
);
CREATE INDEX idx_audit_occurred_at ON audit_events(occurred_at);
CREATE INDEX idx_audit_actor ON audit_events(actor_user_id);
CREATE INDEX idx_audit_action ON audit_events(action);

CREATE FUNCTION audit_events_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'audit_events es de solo anexado';
END;
$$;
CREATE TRIGGER audit_events_no_change
    BEFORE UPDATE OR DELETE ON audit_events
    FOR EACH ROW EXECUTE FUNCTION audit_events_append_only();

CREATE TABLE model_usage (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),
    user_id uuid,
    provider text NOT NULL,
    model text NOT NULL,
    status text NOT NULL CHECK (status IN ('ok', 'error', 'denied')),
    input_tokens integer,
    output_tokens integer,
    latency_ms double precision,
    cost_usd double precision,
    error_kind text
);
CREATE INDEX idx_model_usage_created ON model_usage(created_at);
CREATE INDEX idx_model_usage_user ON model_usage(user_id, created_at);
