import { api, onUnauthorized } from "./api.js";
import { defineRoutes, dropShell, navigate, startRouter } from "./router.js";
import { rememberConversation, setNotice, setUser } from "./state.js";
import { adminView } from "./views/admin.js";
import { chatView } from "./views/chat.js";
import { dashboardView } from "./views/dashboard.js";
import { developerView } from "./views/developer.js";
import { loginView } from "./views/login.js";
import { organizationsView } from "./views/organizations.js";
import { profileView } from "./views/profile.js";
import { registerView } from "./views/register.js";

export async function boot(root) {
  defineRoutes([
    { pattern: /^\/login$/, guest: true, view: loginView },
    { pattern: /^\/register$/, guest: true, view: registerView },
    { pattern: /^\/dashboard$/, nav: "dashboard", view: dashboardView },
    { pattern: /^\/chat(?:\/([^/]+))?$/, nav: "chat", view: chatView },
    { pattern: /^\/developer$/, nav: "developer", view: developerView },
    { pattern: /^\/organizations$/, nav: "organizations", view: organizationsView },
    { pattern: /^\/admin$/, nav: "admin", admin: true, view: adminView },
    { pattern: /^\/profile$/, nav: null, view: profileView },
  ]);

  // Sesión caducada en cualquier llamada autenticada: volver al acceso con un aviso.
  onUnauthorized(() => {
    setUser(null);
    rememberConversation(null);
    setNotice("Tu sesión ha caducado. Inicia sesión de nuevo.");
    dropShell();
    navigate("/login");
  });

  try {
    const data = await api.me();
    setUser(data.user);
  } catch {
    setUser(null);
  }
  await startRouter(root);
}
