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
