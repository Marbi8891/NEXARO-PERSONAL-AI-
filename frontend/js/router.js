// Enrutador por hash (#/ruta): no necesita configuración en el servidor.
import { clear } from "./dom.js";
import { getUser } from "./state.js";
import { createShell } from "./shell.js";

const routes = [];
let root = null;
let shell = null;
let cleanup = null;

export function defineRoutes(list) {
  routes.length = 0;
  routes.push(...list);
}

export function navigate(path) {
  const target = `#${path}`;
  if (location.hash === target) render();
  else location.hash = target;
}

function currentPath() {
  return location.hash.slice(1) || "/";
}

function match(path) {
  for (const route of routes) {
    const found = route.pattern.exec(path);
    if (found) return { route, params: found.slice(1).map((part) => (part ? decodeURIComponent(part) : part)) };
  }
  return null;
}

function leave() {
  if (typeof cleanup === "function") cleanup();
  cleanup = null;
}

export function dropShell() {
  leave();
  shell?.destroy();
  shell = null;
}

export async function render() {
  const user = getUser();
  const found = match(currentPath());
  const route = found?.route;

  // Guardas: invitados solo ven acceso/registro; usuarios ven la app; administración exige rol.
  if (!user && !route?.guest) return navigate("/login");
  if (user && (route?.guest || !route)) return navigate("/chat");
  if (route?.admin && user.role !== "admin") return navigate("/chat");

  leave();
  if (route.guest) {
    dropShell();
    clear(root);
    cleanup = await route.view({ container: root, params: found.params });
    return;
  }

  if (!shell) {
    shell = createShell({ user });
    clear(root).append(shell.element);
  }
  shell.setActive(route.nav);
  clear(shell.main);
  clear(shell.sidebarSlot);
  cleanup = await route.view({ container: shell.main, sidebar: shell.sidebarSlot, params: found.params, shell });
}

export function startRouter(container) {
  root = container;
  window.addEventListener("hashchange", render);
  return render();
}
