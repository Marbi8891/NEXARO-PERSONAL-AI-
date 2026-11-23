-- Propiedad de conversaciones (docs/security/CONVERSATION_ISOLATION.md). Misma regla que
-- sqlite/0013_conversation_ownership.sql. NOT VALID: se aplica a filas nuevas y modificadas sin
-- validar ni tocar las antiguas (las huérfanas se recuperan de forma explícita, nunca aquí).

ALTER TABLE conversations
    ADD CONSTRAINT conversations_user_id_required CHECK (user_id IS NOT NULL) NOT VALID;

CREATE FUNCTION conversations_owner_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.user_id IS NOT NULL AND NEW.user_id IS DISTINCT FROM OLD.user_id THEN
        RAISE EXCEPTION 'conversations.user_id no se puede cambiar';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER conversations_owner_immutable
    BEFORE UPDATE OF user_id ON conversations
    FOR EACH ROW EXECUTE FUNCTION conversations_owner_immutable();

CREATE FUNCTION messages_conversation_owned() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM conversations WHERE id = NEW.conversation_id AND user_id IS NOT NULL
    ) THEN
        RAISE EXCEPTION 'messages.conversation_id requiere una conversación con propietario';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER messages_conversation_owned
    BEFORE INSERT ON messages
    FOR EACH ROW EXECUTE FUNCTION messages_conversation_owned();

CREATE INDEX IF NOT EXISTS idx_conversations_user_org ON conversations(user_id, organization_id);
