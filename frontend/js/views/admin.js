import { api } from "../api.js";
import { clear, formatDate, h } from "../dom.js";

const STATUS = { approved: ["ok", "Aprobado"], pending: ["warn", "Pendiente"], rejected: ["bad", "Rechazado"] };

export function adminView({ container }) {
  const toast = h("p", { class: "toast", role: "status", hidden: true });
  const panel = h("div", { id: "admin-panel", role: "tabpanel" });
  const tabs = [
    ["users", "Usuarios", usersPanel],
    ["audit", "Auditoría", auditPanel],
    ["usage", "Uso del modelo", usagePanel],
  ];
  const buttons = tabs.map(([key, label, render]) =>
    h("button", { type: "button", role: "tab", "aria-selected": "false", onclick: () => select(key, render) }, label),
  );

  function notify(message, isError = false) {
    toast.hidden = !message;
    toast.textContent = message;
    toast.className = isError ? "toast error" : "toast";
  }

  async function guarded(action, success) {
    try {
      await action();
      notify(success);
    } catch (error) {
      notify(error.message, true);
    }
  }

  async function select(key, render) {
    tabs.forEach(([k], index) => buttons[index].setAttribute("aria-selected", String(k === key)));
    clear(panel).append(h("p", { class: "empty" }, "Cargando..."));
    try {
      await render(panel, guarded);
    } catch (error) {
      clear(panel).append(h("p", { class: "toast error" }, error.message));
    }
  }

  container.append(
    h("header", { class: "page-header" }, h("h1", {}, "Administración")),
    h("div", { class: "page-body" }, h("div", { class: "tabs", role: "tablist" }, buttons), toast, panel),
  );
  return select("users", usersPanel);
}

async function usersPanel(panel, guarded) {
  const reload = () => usersPanel(panel, guarded);
  const { users, public_registration_enabled: open } = await api.adminUsers();

  const toggle = h(
    "button",
    { class: "button secondary", type: "button", onclick: () => guarded(async () => { await api.adminSetRegistration(!open); await reload(); }, open ? "Registro público desactivado." : "Registro público activado.") },
    open ? "Cerrar registro" : "Abrir registro",
  );
  const email = h("input", { id: "new-email", type: "email", required: true, autocomplete: "off" });
  const password = h("input", { id: "new-password", type: "password", required: true, minlength: "12", autocomplete: "new-password" });

  const create = h(
    "form",
    {
      class: "inline-form",
      onsubmit: (event) => {
        event.preventDefault();
        guarded(async () => {
          await api.adminCreateUser(email.value.trim(), password.value);
          await reload();
        }, "Usuario creado.");
      },
    },
    h("div", {}, h("label", { for: "new-email" }, "Correo"), email),
    h("div", {}, h("label", { for: "new-password" }, "Contraseña (mín. 12)"), password),
    h("button", { class: "button primary", type: "submit" }, "Crear usuario"),
  );

  const act = (label, run, message) =>
    h("button", { class: "button secondary small", type: "button", onclick: () => guarded(async () => { await run(); await reload(); }, message) }, label);

  const rows = users.map((user) => {
    const [tone, label] = STATUS[user.approval_status] ?? ["warn", user.approval_status];
    const buttons = [];
    if (user.approval_status === "pending") {
      buttons.push(act("Aprobar", () => api.adminApprove(user.id), "Usuario aprobado."), act("Rechazar", () => api.adminReject(user.id), "Usuario rechazado."));
    }
    if (user.approval_status === "approved") {
      buttons.push(
        user.is_active
          ? act("Desactivar", () => api.adminSetActive(user.id, false), "Usuario desactivado.")
          : act("Activar", () => api.adminSetActive(user.id, true), "Usuario activado."),
      );
    }
    return h(
      "tr",
      {},
      h("td", {}, user.email),
      h("td", {}, user.role),
      h("td", {}, h("span", { class: `badge ${tone}` }, label), " ", h("span", { class: `badge ${user.is_active ? "ok" : "bad"}` }, user.is_active ? "Activo" : "Inactivo")),
      h("td", {}, formatDate(user.created_at)),
      h("td", { class: "actions" }, buttons),
    );
  });

  clear(panel).append(
    h("section", { class: "card" }, h("div", { class: "switch-row" }, h("div", {}, h("h2", {}, "Registro público"), h("p", {}, open ? "Abierto: cualquiera puede solicitar acceso (requiere aprobación)." : "Cerrado: solo los administradores crean cuentas.")), toggle)),
    h("section", { class: "card" }, h("h2", {}, "Crear usuario"), create),
    h(
      "div",
      { class: "table-wrap" },
      h("table", {}, h("caption", {}, "Usuarios"), h("thead", {}, h("tr", {}, ["Correo", "Rol", "Estado", "Alta", "Acciones"].map((t) => h("th", { scope: "col" }, t)))), h("tbody", {}, rows)),
    ),
  );
}

async function auditPanel(panel) {
  const filter = h("input", { id: "audit-filter", type: "text", placeholder: "p. ej. auth.login", maxlength: "64" });
  const body = h("div", { class: "table-wrap" });

  async function load() {
    const { events } = await api.adminAudit(filter.value.trim());
    clear(body).append(
      events.length
        ? h(
            "table",
            {},
            h("caption", {}, "Eventos recientes"),
            h("thead", {}, h("tr", {}, ["Fecha", "Acción", "Resultado", "Objetivo", "IP"].map((t) => h("th", { scope: "col" }, t)))),
            h("tbody", {}, events.map((e) => h("tr", {}, h("td", {}, formatDate(e.occurred_at)), h("td", { class: "mono" }, e.action), h("td", {}, h("span", { class: `badge ${e.outcome === "success" ? "ok" : "bad"}` }, e.outcome)), h("td", { class: "mono" }, [e.target_type, e.target_id].filter(Boolean).join(":")), h("td", { class: "mono" }, e.ip ?? "")))),
          )
        : h("p", { class: "empty" }, "No hay eventos."),
    );
  }

  clear(panel).append(
    h("form", { class: "inline-form", onsubmit: (event) => { event.preventDefault(); load().catch((e) => clear(body).append(h("p", { class: "toast error" }, e.message))); } }, h("div", {}, h("label", { for: "audit-filter" }, "Filtrar por acción"), filter), h("button", { class: "button secondary", type: "submit" }, "Filtrar")),
    body,
  );
  await load();
}

async function usagePanel(panel) {
  const { usage, month_cost_usd: cost } = await api.adminUsage();
  clear(panel).append(
    h("section", { class: "card" }, h("h2", {}, "Coste del mes (USD)"), h("p", { class: "mono" }, Number(cost ?? 0).toFixed(4))),
    h(
      "div",
      { class: "table-wrap" },
      usage.length
        ? h("table", {}, h("caption", {}, "Uso por modelo"), h("thead", {}, h("tr", {}, ["Proveedor", "Modelo", "Estado", "Peticiones", "Tokens in", "Tokens out", "Coste"].map((t) => h("th", { scope: "col" }, t)))), h("tbody", {}, usage.map((u) => h("tr", {}, h("td", {}, u.provider), h("td", { class: "mono" }, u.model), h("td", {}, u.status), h("td", {}, u.requests), h("td", {}, u.input_tokens), h("td", {}, u.output_tokens), h("td", { class: "mono" }, Number(u.cost_usd).toFixed(4))))))
        : h("p", { class: "empty" }, "Sin uso registrado."),
    ),
  );
}
