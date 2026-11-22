-- Propiedad de conversaciones (docs/security/CONVERSATION_ISOLATION.md). Ver postgresql/0008.
-- SQLite no permite cambiar `user_id` a NOT NULL sin reconstruir la tabla, y una base viva no se
-- reconstruye: los triggers imponen la regla a partir de ahora y las filas antiguas NO se tocan
-- (las huérfanas siguen invisibles: ninguna consulta casa `user_id = ?` con NULL).

-- Toda conversación nueva tiene propietario.
CREATE TRIGGER conversations_owner_required BEFORE INSERT ON conversations
WHEN NEW.user_id IS NULL
BEGIN
    SELECT RAISE(ABORT, 'conversations.user_id es obligatorio');
END;

-- La propiedad no cambia de manos. Solo se permite dar dueño a una huérfana (NULL -> usuario):
-- es la recuperación explícita de bootstrap_admin --assign-orphaned-conversations.
CREATE TRIGGER conversations_owner_immutable BEFORE UPDATE OF user_id ON conversations
WHEN OLD.user_id IS NOT NULL AND (NEW.user_id IS NULL OR NEW.user_id <> OLD.user_id)
BEGIN
    SELECT RAISE(ABORT, 'conversations.user_id no se puede cambiar');
END;

-- Un mensaje solo entra en una conversación con propietario.
CREATE TRIGGER messages_conversation_owned BEFORE INSERT ON messages
WHEN NOT EXISTS (
    SELECT 1 FROM conversations WHERE id = NEW.conversation_id AND user_id IS NOT NULL
)
BEGIN
    SELECT RAISE(ABORT, 'messages.conversation_id requiere una conversación con propietario');
END;

-- Listados por usuario y origen (web: organization_id NULL; API: organización de la clave).
CREATE INDEX IF NOT EXISTS idx_conversations_user_org ON conversations(user_id, organization_id);
