// Estado mínimo compartido: usuario autenticado y aviso para la pantalla de acceso (persiste hasta enviar el formulario).
let user = null;
let notice = "";

export const getUser = () => user;
export const setUser = (next) => {
  user = next;
};

export function setNotice(message) {
  notice = message;
}
export const getNotice = () => notice;

// Comodidad de UI, no seguridad: el backend comprueba siempre la propiedad (404 si es ajena).
// Se guarda junto al id del usuario para no intentar abrir la conversación de otra cuenta que
// usó este navegador sin cerrar sesión (cookie caducada, navegador cerrado...).
const CONVERSATION_KEY = "nexaro_conversation_id";
export function rememberConversation(id) {
  try {
    if (id && user?.id) localStorage.setItem(CONVERSATION_KEY, JSON.stringify({ user: user.id, id }));
    else localStorage.removeItem(CONVERSATION_KEY);
  } catch {
    // Almacenamiento no disponible: la app funciona igual, solo no recuerda la conversación.
  }
}
export function rememberedConversation() {
  try {
    const saved = JSON.parse(localStorage.getItem(CONVERSATION_KEY) ?? "null");
    if (saved && typeof saved === "object" && saved.user === user?.id && typeof saved.id === "string") return saved.id;
    localStorage.removeItem(CONVERSATION_KEY); // de otra cuenta o del formato antiguo (solo el id)
    return null;
  } catch {
    return null;
  }
}

// Agente del chat (ADR-0022). `nexaro_chat_mode` es la clave del antiguo selector de modo
// (general | tutor): se lee una vez para no perder la elección al actualizar.
const AGENT_KEY = "nexaro_chat_agent";
const LEGACY_MODE_KEY = "nexaro_chat_mode";
export function rememberAgent(agent) {
  try {
    localStorage.setItem(AGENT_KEY, agent);
  } catch {
    // Sin almacenamiento: el agente vuelve a «general» al recargar.
  }
}
export function rememberedAgent() {
  try {
    return localStorage.getItem(AGENT_KEY) || localStorage.getItem(LEGACY_MODE_KEY) || "general";
  } catch {
    return "general";
  }
}

// Modelo elegido para las conversaciones nuevas («auto» = el configurado con sus respaldos).
// El de cada conversación lo guarda el servidor.
const MODEL_KEY = "nexaro_chat_model";
export function rememberModel(model) {
  try {
    localStorage.setItem(MODEL_KEY, model);
  } catch {
    // Sin almacenamiento: las conversaciones nuevas empiezan en «auto».
  }
}
export function rememberedModel() {
  try {
    return localStorage.getItem(MODEL_KEY) || "auto";
  } catch {
    return "auto";
  }
}

// Borrador para el chat (biblioteca de prompts → chat). Solo en memoria: se consume una vez.
let chatDraft = "";
export function setChatDraft(text) {
  chatDraft = text;
}
export function takeChatDraft() {
  const text = chatDraft;
  chatDraft = "";
  return text;
}
