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

const CONVERSATION_KEY = "nexaro_conversation_id";
export function rememberConversation(id) {
  try {
    if (id) localStorage.setItem(CONVERSATION_KEY, id);
    else localStorage.removeItem(CONVERSATION_KEY);
  } catch {
    // Almacenamiento no disponible: la app funciona igual, solo no recuerda la conversación.
  }
}
export function rememberedConversation() {
  try {
    return localStorage.getItem(CONVERSATION_KEY);
  } catch {
    return null;
  }
}

const MODE_KEY = "nexaro_chat_mode";
export const CHAT_MODES = ["general", "tutor"];
export function rememberMode(mode) {
  try {
    localStorage.setItem(MODE_KEY, mode);
  } catch {
    // Sin almacenamiento: el modo vuelve a «general» al recargar.
  }
}
export function rememberedMode() {
  try {
    const mode = localStorage.getItem(MODE_KEY);
    return CHAT_MODES.includes(mode) ? mode : "general";
  } catch {
    return "general";
  }
}
