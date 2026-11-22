-- Modelo elegido para la conversación. Ver postgresql/0009_conversation_model.sql.
-- NULL: modo automático (modelo configurado y rutas de respaldo).
ALTER TABLE conversations ADD COLUMN model TEXT;
