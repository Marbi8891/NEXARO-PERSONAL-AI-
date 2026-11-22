-- Permisos (scopes) por clave de API (ADR-0011). Ver postgresql/0004_api_key_scopes.sql.
-- Lista separada por comas validada por la aplicación; las claves existentes conservan lo único
-- que podían hacer hasta ahora: chat:write.
ALTER TABLE api_keys ADD COLUMN scopes TEXT NOT NULL DEFAULT 'chat:write';
