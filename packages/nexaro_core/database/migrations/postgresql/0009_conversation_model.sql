-- Modelo elegido para la conversación. Misma columna que sqlite/0009_conversation_model.sql.
ALTER TABLE conversations ADD COLUMN model text;
