-- Permisos (scopes) por clave de API (ADR-0011). Mismas columnas que sqlite/0004_api_key_scopes.sql.
ALTER TABLE api_keys ADD COLUMN scopes text NOT NULL DEFAULT 'chat:write';
