// Marco de la aplicación: barra lateral (navegación y estado del modelo), cabecera y contenido.
import { api } from "./api.js";
import { brand } from "./components/brand.js";
import { notificationBell } from "./components/notifications.js";
import { userMenu } from "./components/user-menu.js";
import { clear, h } from "./dom.js";
import { rememberConversation, setNotice, setUser } from "./state.js";

const HEALTH_INTERVAL_MS = 60_000;

export function createShell({ user }) {
  const dot = h("span", { class: "dot", "aria-hidden": "true" });
  const statusText = h("span", {}, "Comprobando conexión...");

  const links = [
    { nav: "dashboard", href: "#/dashboard", label: "Panel" },
    { nav: "chat", href: "#/chat", label: "Chat" },
    { nav: "organizations", href: "#/organizations", label: "Organizaciones" },
    { nav: "developer", href: "#/developer", label: "Developer" },
    ...(user.role === "admin"
      ? [
          { nav: "security", href: "#/security", label: "Seguridad" },
          { nav: "admin", href: "#/admin", label: "Administración" },
        ]
      : []),
  ].map((link) => h("a", { href: link.href, "data-nav": link.nav, onclick: () => setDrawer(false) }, link.label));

  const sidebarSlot = h("div", { class: "sidebar-slot" });
  const main = h("main", { class: "main", id: "view", tabindex: "-1" });
  const title = h("h1", { id: "page-title" });
  const topbarActions = h("div", { class: "topbar-actions" });

  const menu = userMenu({ user, onLogout: logout });
  const bell = notificationBell();
  topbarActions.append(bell.element, menu.element);

  const menuButton = h("button", { class: "menu-button", type: "button", "aria-controls": "sidebar", "aria-expanded": "false", "aria-label": "Abrir navegación", onclick: () => setDrawer(app.dataset.navOpen !== "true") }, "☰");
  const scrim = h("div", { class: "scrim", onclick: () => setDrawer(false) });
  const sidebar = h(
    "aside",
    { class: "sidebar", id: "sidebar", "aria-label": "Navegación" },
    h("div", { class: "sidebar-head" }, h("div", {}, brand(), h("div", { class: "status", role: "status" }, dot, statusText)), h("button", { class: "drawer-close", type: "button", "aria-label": "Cerrar navegación", onclick: () => { setDrawer(false); menuButton.focus(); } }, "✕")),
    h("nav", { class: "nav", "aria-label": "Principal" }, links),
    sidebarSlot,
  );
  const app = h("div", { class: "app" }, scrim, sidebar, h("div", { class: "content" }, h("header", { class: "topbar" }, menuButton, title, topbarActions), main));

  function setDrawer(open) {
    app.dataset.navOpen = String(open);
    menuButton.setAttribute("aria-expanded", String(open));
    menuButton.setAttribute("aria-label", open ? "Cerrar navegación" : "Abrir navegación");
  }
  const onEscape = (event) => {
    if (event.key === "Escape" && app.dataset.navOpen === "true") {
      setDrawer(false);
      menuButton.focus();
    }
  };
  document.addEventListener("keydown", onEscape);
  setDrawer(false);

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
    try {
      await api.logout();
    } catch (error) {
      if (error.status !== 401) {
        const { toast } = await import("./components/toast.js");
        toast("No se pudo cerrar la sesión. Inténtalo de nuevo.", { error: true });
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
    element: app,
    main,
    sidebarSlot,
    topbarActions,
    refreshHealth: checkHealth,
    logout,
    setTitle(text) {
      title.textContent = text;
      document.title = `${text} · NEXARO`;
    },
    setActive(nav) {
      setDrawer(false);
      menu.close();
      bell.refresh();
      for (const link of links) {
        if (link.dataset.nav === nav) link.setAttribute("aria-current", "page");
        else link.removeAttribute("aria-current");
      }
    },
    destroy() {
      clearInterval(timer);
      document.removeEventListener("keydown", onEscape);
      menu.destroy();
      bell.destroy();
      clear(app);
    },
  };
}
