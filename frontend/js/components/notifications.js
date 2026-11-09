// Campana de avisos de la cabecera. Los avisos se derivan del estado real (/api/notifications);
// no hay avisos de relleno: sin avisos, el panel lo dice.
import { api } from "../api.js";
import { clear, h } from "../dom.js";

const NS = "http://www.w3.org/2000/svg";

function bellIcon() {
  const svg = document.createElementNS(NS, "svg");
  for (const [k, v] of Object.entries({ viewBox: "0 0 24 24", width: "20", height: "20", fill: "none", stroke: "currentColor", "stroke-width": "2", "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true" })) svg.setAttribute(k, v);
  for (const d of ["M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9", "M10.3 21a1.9 1.9 0 0 0 3.4 0"]) {
    const path = document.createElementNS(NS, "path");
    path.setAttribute("d", d);
    svg.append(path);
  }
  return svg;
}

const SEVERITY_LABEL = { error: "Error", warning: "Atención", info: "Información" };

export function notificationBell() {
  const count = h("span", { class: "bell-count", hidden: true });
  const trigger = h(
    "button",
    { class: "bell-trigger", type: "button", "aria-expanded": "false", "aria-controls": "notifications-panel", "aria-label": "Avisos", onclick: () => setOpen(panel.hidden) },
    bellIcon(),
    count,
  );
  const list = h("ul", { class: "notice-list" });
  const panel = h("div", { class: "menu notice-panel", id: "notifications-panel", hidden: true }, h("h2", { class: "menu-title" }, "Avisos"), list);
  const element = h("div", { class: "user-menu" }, trigger, panel);

  function setOpen(open) {
    panel.hidden = !open;
    trigger.setAttribute("aria-expanded", String(open));
  }

  function render(items) {
    clear(list);
    if (items.length === 0) list.append(h("li", { class: "notice-empty" }, "No hay avisos."));
    for (const item of items) {
      const body = [h("strong", {}, item.title), h("span", {}, item.text)];
      list.append(
        h(
          "li",
          { class: `notice ${item.severity}` },
          h("span", { class: "notice-kind" }, SEVERITY_LABEL[item.severity] ?? "Aviso"),
          item.href ? h("a", { href: item.href, onclick: () => setOpen(false) }, body) : h("div", {}, body),
        ),
      );
    }
    count.hidden = items.length === 0;
    count.textContent = String(items.length);
    trigger.setAttribute("aria-label", items.length ? `Avisos (${items.length} sin resolver)` : "Avisos (ninguno)");
  }

  async function refresh() {
    try {
      render((await api.notifications()).notifications);
    } catch {
      clear(list);
      list.append(h("li", { class: "notice-empty" }, "No se pudieron cargar los avisos."));
    }
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
  refresh();

  return {
    element,
    refresh,
    destroy() {
      document.removeEventListener("click", outside);
      document.removeEventListener("keydown", escape);
    },
  };
}
