import { api } from "../api.js";
import { clear, formatDate, h } from "../dom.js";
import { navigate } from "../router.js";
import { rememberConversation, rememberedConversation } from "../state.js";

export async function chatView({ container, sidebar, params, shell }) {
  shell.setTitle("Chat");
  let conversationId = params[0] || null;
  let sending = false;

  const messages = h("div", { class: "messages", role: "log", "aria-live": "polite" });
  const input = h("textarea", { id: "message", rows: "2", placeholder: "Escribe tu mensaje...", "aria-label": "Mensaje", maxlength: "8000" });
  const send = h("button", { class: "button primary", type: "submit" }, "Enviar");
  const list = h("div", { class: "conversation-list" });
  const startNew = () => {
    rememberConversation(null);
    navigate("/chat");
  };
  const newChat = h("button", { class: "button secondary", type: "button", onclick: startNew }, "+ Nueva conversación");

  sidebar.append(newChat, h("h2", { class: "history-heading" }, "Historial"), list);

  function welcome() {
    clear(messages).append(
      h("div", { class: "welcome" }, h("h2", {}, "¿En qué puedo ayudarte?"), h("p", {}, "Tus conversaciones se guardan en tu cuenta y solo tú puedes verlas.")),
    );
  }

  function addMessage(role, text) {
    messages.querySelector(".welcome")?.remove();
    const node = h("div", { class: `message ${role}` }, text);
    messages.append(node);
    messages.scrollTop = messages.scrollHeight;
    return node;
  }

  async function loadHistory() {
    try {
      const { conversations } = await api.conversations();
      clear(list);
      if (!conversations.length) list.append(h("div", { class: "history-empty" }, "Aún no hay conversaciones."));
      for (const item of conversations) {
        const active = item.id === conversationId;
        list.append(
          h(
            "button",
            { class: `history-item${active ? " active" : ""}`, type: "button", "aria-current": active ? "true" : null, onclick: () => navigate(`/chat/${encodeURIComponent(item.id)}`) },
            h("span", { class: "history-title" }, item.title || item.preview || "Conversación"),
            h("span", { class: "history-meta" }, `${item.message_count} mensajes · ${formatDate(item.last_activity)}`),
          ),
        );
      }
    } catch (error) {
      clear(list).append(h("div", { class: "history-empty" }, error.message));
    }
  }

  async function openConversation(id) {
    try {
      const data = await api.conversation(id);
      conversationId = id;
      rememberConversation(id);
      clear(messages);
      for (const message of data.messages) addMessage(message.role === "user" ? "user" : "assistant", message.content);
    } catch (error) {
      if (error.status === 404) {
        rememberConversation(null);
        conversationId = null;
        welcome();
        navigate("/chat");
        return;
      }
      clear(messages);
      addMessage("assistant error", error.message);
    }
  }

  async function onSubmit(event) {
    event.preventDefault();
    const text = input.value.trim();
    if (!text || sending) return;
    sending = true;
    send.disabled = true;
    input.value = "";
    addMessage("user", text);
    const pending = addMessage("assistant", "Pensando...");
    try {
      const data = await api.chat(text, conversationId);
      pending.textContent = data.answer;
      const isNew = data.conversation_id !== conversationId;
      conversationId = data.conversation_id;
      rememberConversation(conversationId);
      if (isNew) history.replaceState(null, "", `#/chat/${encodeURIComponent(conversationId)}`);
      await loadHistory();
      shell.refreshHealth();
    } catch (error) {
      pending.className = "message assistant error";
      pending.textContent = error.message;
    } finally {
      sending = false;
      send.disabled = false;
      input.focus();
    }
  }

  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      send.click();
    }
  });

  container.append(
    h(
      "div",
      { class: "chat-main" },
      messages,
      h(
        "div",
        { class: "composer-wrap" },
        h("form", { class: "composer", onsubmit: onSubmit }, input, send),
        h("div", { class: "composer-hint" }, "Enter envía · Mayús+Enter salta de línea"),
      ),
    ),
  );

  // Restaurar la última conversación al entrar en /chat sin id.
  if (!conversationId) {
    const remembered = rememberedConversation();
    if (remembered) {
      await openConversation(remembered);
      if (conversationId) history.replaceState(null, "", `#/chat/${encodeURIComponent(conversationId)}`);
    } else welcome();
  } else await openConversation(conversationId);
  await loadHistory();
  input.focus();
}
