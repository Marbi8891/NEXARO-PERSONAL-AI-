import { api } from "../api.js";
import { confirmDialog } from "../components/dialog.js";
import { toast } from "../components/toast.js";
import { clear, formatDate, h } from "../dom.js";
import { renderMarkdown } from "../markdown.js";
import { navigate } from "../router.js";
import { rememberConversation, rememberedConversation } from "../state.js";

export async function chatView({ container, sidebar, params, shell }) {
  shell.setTitle("Chat");
  let conversationId = params[0] || null;
  let sending = false;
  let controller = null;

  const messages = h("div", { class: "messages", role: "log", "aria-live": "polite" });
  const input = h("textarea", { id: "message", rows: "2", placeholder: "Escribe tu mensaje...", "aria-label": "Mensaje", maxlength: "8000" });
  const send = h("button", { class: "button primary", type: "submit" }, "Enviar");
  // Documentos: opt-in. Solo se muestra si el usuario pertenece a alguna organización.
  const useDocuments = h("input", { id: "use-documents", type: "checkbox" });
  const documentsOrg = h("select", { id: "documents-org", "aria-label": "Organización de los documentos", hidden: true });
  const documentsBar = h("label", { class: "docs-toggle", hidden: true }, useDocuments, h("span", {}, "Consultar mis documentos"), documentsOrg);
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
    const markdown = role === "assistant";
    const node = h("div", { class: `message ${role}${markdown ? " md" : ""}` });
    if (markdown) node.append(...renderMarkdown(text));
    else node.textContent = text;
    messages.append(node);
    messages.scrollTop = messages.scrollHeight;
    return node;
  }

  function addNote(parent, text, kind = "note") {
    parent.append(h("div", { class: `message-note ${kind}` }, text));
  }

  function addSources(parent, sources) {
    if (!sources.length) return addNote(parent, "No hay fragmentos relevantes en tus documentos para este mensaje.");
    parent.append(
      h(
        "details",
        { class: "message-sources" },
        h("summary", {}, `Fuentes (${sources.length})`),
        h("ol", { class: "sources" }, sources.map((s) => h("li", {}, h("strong", {}, s.title), h("span", { class: "hint" }, ` · fragmento ${s.ordinal + 1}`), h("p", {}, s.snippet)))),
      ),
    );
  }

  async function loadOrganizations() {
    try {
      const { organizations } = await api.organizations();
      if (!organizations.length) return;
      documentsOrg.replaceChildren(...organizations.map((o) => h("option", { value: o.id }, o.name)));
      documentsOrg.hidden = organizations.length < 2;
      documentsBar.hidden = false;
    } catch {
      // Sin organizaciones o sin permiso: el chat funciona igual, sin documentos.
    }
  }

  // Solo se repinta el mensaje en curso, como mucho cada ~60 ms, no todo el historial.
  function liveRenderer(node) {
    let text = "";
    let timer = null;
    const paint = () => {
      timer = null;
      node.replaceChildren(...renderMarkdown(text));
      messages.scrollTop = messages.scrollHeight;
    };
    return {
      push(piece) {
        text += piece;
        if (timer === null) timer = setTimeout(paint, 60);
      },
      flush() {
        if (timer !== null) clearTimeout(timer);
        if (text) paint();
      },
      get text() {
        return text;
      },
    };
  }

  function setSending(value) {
    sending = value;
    send.textContent = value ? "Detener" : "Enviar";
    send.type = value ? "button" : "submit";
    send.classList.toggle("danger", value);
    send.setAttribute("aria-label", value ? "Detener la respuesta" : "Enviar mensaje");
  }

  async function loadHistory() {
    try {
      const { conversations } = await api.conversations();
      clear(list);
      if (!conversations.length) list.append(h("div", { class: "history-empty" }, "Aún no hay conversaciones."));
      for (const item of conversations) {
        const active = item.id === conversationId;
        const title = item.title || item.preview || "Conversación";
        list.append(
          h(
            "div",
            { class: "history-row" },
            h(
              "button",
              { class: `history-item${active ? " active" : ""}`, type: "button", "aria-current": active ? "true" : null, onclick: () => navigate(`/chat/${encodeURIComponent(item.id)}`) },
              h("span", { class: "history-title" }, title),
              h("span", { class: "history-meta" }, `${item.message_count} mensajes · ${formatDate(item.last_activity)}`),
            ),
            h("button", { class: "history-delete", type: "button", "aria-label": `Eliminar la conversación: ${title}`, title: "Eliminar", onclick: () => removeConversation(item.id) }, "×"),
          ),
        );
      }
    } catch (error) {
      clear(list).append(h("div", { class: "history-empty" }, error.message));
    }
  }

  async function removeConversation(id) {
    const confirmed = await confirmDialog({
      title: "Eliminar conversación",
      message: "Se borrarán la conversación y todos sus mensajes. No se puede deshacer.",
      confirmLabel: "Eliminar",
      danger: true,
    });
    if (!confirmed) return;
    try {
      await api.deleteConversation(id);
    } catch (error) {
      if (error.status !== 404) {
        toast(error.message, { error: true });
        return;
      }
    }
    toast("Conversación eliminada.");
    if (id === conversationId) startNew();
    else await loadHistory();
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
    setSending(true);
    input.value = "";
    addMessage("user", text);
    const pending = addMessage("assistant", "Pensando...");
    pending.classList.add("generating");
    pending.setAttribute("aria-busy", "true");
    const live = liveRenderer(pending);
    let started = false;
    let failure = null;
    let truncated = false;
    let aborted = false;
    let sources = null;
    const documentOrganizationId = !documentsBar.hidden && useDocuments.checked ? documentsOrg.value : null;
    controller = new AbortController();
    try {
      await api.chatStream(text, conversationId, {
        signal: controller.signal,
        documentOrganizationId,
        onEvent(item) {
          if (item.event === "start") {
            const isNew = item.conversation_id !== conversationId;
            conversationId = item.conversation_id;
            rememberConversation(conversationId);
            if (isNew) history.replaceState(null, "", `#/chat/${encodeURIComponent(conversationId)}`);
          } else if (item.event === "sources") sources = item.sources;
          else if (item.event === "token") {
            if (!started) {
              started = true;
              pending.replaceChildren();
            }
            live.push(item.content);
          } else if (item.event === "done") truncated = Boolean(item.truncated);
          else if (item.event === "error") failure = item.message;
        },
      });
    } catch (error) {
      if (error?.name === "AbortError") aborted = true;
      else failure = error.message;
    } finally {
      live.flush();
      pending.classList.remove("generating");
      pending.removeAttribute("aria-busy");
      controller = null;
    }
    if (aborted) {
      if (!started) pending.replaceChildren();
      addNote(pending, "Respuesta detenida.");
    } else if (failure) {
      if (!started) {
        pending.className = "message assistant error";
        pending.textContent = failure;
      } else addNote(pending, failure, "error");
    } else if (truncated) addNote(pending, "Respuesta cortada por el límite de longitud. Pídeme que continúe.");
    if (sources && !failure) addSources(pending, sources);
    setSending(false);
    input.focus();
    await loadHistory();
    shell.refreshHealth();
  }

  send.addEventListener("click", () => {
    if (sending) controller?.abort();
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      if (!sending) send.click();
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
        documentsBar,
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
  await loadOrganizations();
  input.focus();
}
