-- Agente que dio cada respuesta (ADR-0022). Ver postgresql/0007_message_agent.sql.
-- NULL en los mensajes del usuario y en las respuestas anteriores a la migración.
ALTER TABLE messages ADD COLUMN agent TEXT;
