// Marco de la aplicación: barra lateral con navegación, estado del modelo y cierre de sesión.
import { api } from "./api.js";
import { clear, h } from "./dom.js";
import { setNotice, setUser, rememberConversation } from "./state.js";

const HEALTH_INTERVAL_MS = 60_000;

export function createShell({ user }) {
  const dot = h("span", { class: "dot", "aria-hidden": "true" });
  const statusText = h("span", {}, "Comprobando conexión...");
  const logoutError = h("span", { role: "alert", "aria-live": "polite" });
  const logoutButton = h("button", { class: "button secondary small", type: "button", onclick: logout }, "Cerrar sesión");

  const links = [
    { nav: "chat", href: "#/chat", label: "Chat" },
    { nav: "organizations", href: "#/organizations", label: "Organizaciones" },
    ...(user.role === "admin" ? [{ nav: "admin", href: "#/admin", label: "Administración" }] : []),
  ].map((link) => h("a", { href: link.href, dataset: undefined, "data-nav": link.nav }, link.label));

  const sidebarSlot = h("div", { class: "sidebar-slot" });
  const main = h("main", { class: "main", id: "view", tabindex: "-1" });

  const element = h(
    "div",
    { class: "app" },
    h(
      "aside",
      { class: "sidebar" },
      h(
        "div",
        {},
        h("div", { class: "brand" }, "NEXARO"),
        h("div", { class: "subtitle" }, "PERSONAL AI"),
        h("div", { class: "status", role: "status" }, dot, statusText),
      ),
      h("nav", { class: "nav", "aria-label": "Principal" }, links),
      sidebarSlot,
      h("div", { class: "sidebar-footer" }, h("span", { class: "who", title: user.email }, user.email), logoutButton, logoutError),
    ),
    main,
  );

  async function checkHealth() {
    try {
      const data = await api.health();
      dot.className = "dot online";
      statusText.textContent = data.ollama === "connected" ? "Conectado · Ollama" : "Modelo disponible";
    } catch {
      dot.className = "dot offline";
      statusText.textContent = "Modelo no disponible";
    }
  }

  async function logout() {
    logoutButton.disabled = true;
    logoutError.textContent = "";
    try {
      await api.logout();
    } catch (error) {
      if (error.status !== 401) {
        logoutError.textContent = "No se pudo cerrar la sesión. Inténtalo de nuevo.";
        logoutButton.disabled = false;
        return;
      }
    }
    rememberConversation(null);
    setUser(null);
    setNotice("");
    location.hash = "#/login";
  }

  checkHealth();
  const timer = setInterval(checkHealth, HEALTH_INTERVAL_MS);

  return {
    element,
    main,
    sidebarSlot,
    refreshHealth: checkHealth,
    setActive(nav) {
      for (const link of links) {
        if (link.dataset.nav === nav) link.setAttribute("aria-current", "page");
        else link.removeAttribute("aria-current");
      }
    },
    destroy() {
      clearInterval(timer);
      clear(element);
    },
  };
}
