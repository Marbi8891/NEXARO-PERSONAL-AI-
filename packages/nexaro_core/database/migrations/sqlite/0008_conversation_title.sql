-- Título elegido por el usuario (renombrar conversación). Ver postgresql/0008_conversation_title.sql.
-- NULL: el título se sigue derivando del primer mensaje del usuario.
ALTER TABLE conversations ADD COLUMN title TEXT;
