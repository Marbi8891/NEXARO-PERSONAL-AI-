-- Agente que dio cada respuesta (ADR-0022). Misma columna que sqlite/0007_message_agent.sql.
ALTER TABLE messages ADD COLUMN agent text;
