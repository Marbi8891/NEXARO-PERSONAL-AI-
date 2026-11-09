// Menú de usuario de la cabecera (patrón de divulgación: botón + panel; Escape y clic fuera lo cierran).
import { h } from "../dom.js";

export function userMenu({ user, onLogout }) {
  const initials = user.email.slice(0, 2).toUpperCase();
  const panel = h(
    "div",
    { class: "menu", id: "user-menu", hidden: true },
    h("div", { class: "menu-who" }, h("strong", {}, user.email), h("span", { class: "badge" }, user.role === "admin" ? "Administrador" : "Usuario")),
    h("a", { class: "menu-item", href: "#/profile", onclick: () => setOpen(false) }, "Perfil"),
    h("button", { class: "menu-item", type: "button", onclick: onLogout }, "Cerrar sesión"),
  );
  const trigger = h(
    "button",
    { class: "user-trigger", type: "button", "aria-expanded": "false", "aria-controls": "user-menu", "aria-label": `Menú de usuario (${user.email})`, onclick: () => setOpen(panel.hidden) },
    h("span", { class: "avatar", "aria-hidden": "true" }, initials),
    h("span", { class: "user-email" }, user.email),
  );
  const element = h("div", { class: "user-menu" }, trigger, panel);

  function setOpen(open) {
    panel.hidden = !open;
    trigger.setAttribute("aria-expanded", String(open));
  }
  const outside = (event) => {
    if (!panel.hidden && !element.contains(event.target)) setOpen(false);
  };
  const escape = (event) => {
    if (event.key === "Escape" && !panel.hidden) {
      setOpen(false);
      trigger.focus();
    }
  };
  document.addEventListener("click", outside);
  document.addEventListener("keydown", escape);

  return {
    element,
    close: () => setOpen(false),
    destroy() {
      document.removeEventListener("click", outside);
      document.removeEventListener("keydown", escape);
    },
  };
}
