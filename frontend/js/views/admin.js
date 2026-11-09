import { api } from "../api.js";
import { confirmDialog } from "../components/dialog.js";
import { field } from "../components/form.js";
import { errorState, loadingState } from "../components/states.js";
import { dataTable } from "../components/table.js";
import { toast } from "../components/toast.js";
import { clear, formatDate, h } from "../dom.js";

const STATUS = { approved: ["ok", "Aprobado"], pending: ["warn", "Pendiente"], rejected: ["bad", "Rechazado"] };

export function adminView({ container, shell }) {
  shell.setTitle("Administración");
  const panel = h("div", { id: "admin-panel", role: "tabpanel" });
  const tabs = [
    ["users", "Usuarios", usersPanel],
    ["audit", "Auditoría", auditPanel],
    ["usage", "Uso del modelo", usagePanel],
  ];
  const buttons = tabs.map(([key, label, render]) => h("button", { type: "button", role: "tab", "aria-selected": "false", onclick: () => select(key, render) }, label));

  async function select(key, render) {
    tabs.forEach(([k], index) => buttons[index].setAttribute("aria-selected", String(k === key)));
    clear(panel).append(loadingState());
    try {
      await render(panel);
    } catch (error) {
      clear(panel).append(errorState(error.message, { onRetry: () => select(key, render) }));
    }
  }

  container.append(h("div", { class: "page-body" }, h("div", { class: "tabs", role: "tablist" }, buttons), panel));
  return select("users", usersPanel);
}

async function usersPanel(panel) {
  const registrationCard = h("section", { class: "card" });
  let registrationOpen = false;

  async function guarded(action, success) {
    try {
      await action();
      toast(success);
      await refresh();
    } catch (error) {
      toast(error.message, { error: true });
    }
  }
  const act = (label, run, success, confirm) =>
    h("button", { class: "button secondary small", type: "button", onclick: async () => { if (confirm && !(await confirmDialog(confirm))) return; guarded(run, success); } }, label);

  function renderRegistration() {
    clear(registrationCard).append(
      h(
        "div",
        { class: "switch-row" },
        h("div", {}, h("h2", {}, "Registro público"), h("p", {}, registrationOpen ? "Abierto: cualquiera puede solicitar acceso (requiere aprobación)." : "Cerrado: solo los administradores crean cuentas.")),
        h("button", { class: "button secondary", type: "button", onclick: () => guarded(() => api.adminSetRegistration(!registrationOpen), registrationOpen ? "Registro público desactivado." : "Registro público activado.") }, registrationOpen ? "Cerrar registro" : "Abrir registro"),
      ),
    );
  }

  const email = field({ id: "new-email", label: "Correo", type: "email", required: true, autocomplete: "off" });
  const password = field({ id: "new-password", label: "Contraseña", type: "password", required: true, minlength: "12", autocomplete: "new-password", hint: "Mínimo 12 caracteres." });
  const create = h(
    "form",
    {
      class: "inline-form",
      onsubmit: (event) => {
        event.preventDefault();
        guarded(async () => {
          await api.adminCreateUser(email.input.value.trim(), password.input.value);
          email.input.value = "";
          password.input.value = "";
        }, "Usuario creado.");
      },
    },
    email.element,
    password.element,
    h("button", { class: "button", type: "submit" }, "Crear usuario"),
  );

  const table = dataTable({
    caption: "Usuarios",
    initialSort: { key: "created_at", dir: -1 },
    filters: [
      { key: "role", label: "Rol", options: [["admin", "Administrador"], ["user", "Usuario"]] },
      { key: "approval_status", label: "Estado", options: [["approved", "Aprobado"], ["pending", "Pendiente"], ["rejected", "Rechazado"]] },
    ],
    empty: { title: "Sin usuarios", text: "Crea el primero con el formulario de arriba." },
    columns: [
      { key: "email", label: "Correo" },
      { key: "role", label: "Rol" },
      {
        key: "approval_status",
        label: "Estado",
        value: (u) => `${STATUS[u.approval_status]?.[1] ?? u.approval_status} ${u.is_active ? "Activo" : "Inactivo"}`,
        render: (u) => {
          const [tone, label] = STATUS[u.approval_status] ?? ["warn", u.approval_status];
          return [h("span", { class: `badge ${tone}` }, label), " ", h("span", { class: `badge ${u.is_active ? "ok" : "bad"}` }, u.is_active ? "Activo" : "Inactivo")];
        },
      },
      { key: "created_at", label: "Alta", value: (u) => formatDate(u.created_at) },
      {
        key: "actions",
        label: "Acciones",
        sortable: false,
        search: false,
        className: "actions",
        render: (u) => {
          const buttons = [];
          if (u.approval_status === "pending") {
            buttons.push(
              act("Aprobar", () => api.adminApprove(u.id), "Usuario aprobado."),
              act("Rechazar", () => api.adminReject(u.id), "Usuario rechazado.", { title: "¿Rechazar solicitud?", message: `Se rechazará la solicitud de ${u.email}.`, confirmLabel: "Rechazar", danger: true }),
            );
          }
          if (u.approval_status === "approved") {
            buttons.push(
              u.is_active
                ? act("Desactivar", () => api.adminSetActive(u.id, false), "Usuario desactivado.", { title: "¿Desactivar usuario?", message: `${u.email} no podrá iniciar sesión y sus sesiones se cerrarán.`, confirmLabel: "Desactivar", danger: true })
                : act("Activar", () => api.adminSetActive(u.id, true), "Usuario activado."),
            );
          }
          return buttons;
        },
      },
    ],
  });

  async function refresh() {
    const data = await api.adminUsers();
    registrationOpen = data.public_registration_enabled;
    renderRegistration();
    table.setRows(data.users);
  }

  clear(panel).append(registrationCard, h("section", { class: "card" }, h("h2", {}, "Crear usuario"), create), table.element);
  await refresh();
}

async function auditPanel(panel) {
  const action = field({ id: "audit-filter", label: "Filtrar por acción (servidor)", type: "text", placeholder: "p. ej. auth.login", maxlength: "64" });
  const table = dataTable({
    caption: "Eventos recientes",
    initialSort: { key: "occurred_at", dir: -1 },
    filters: [{ key: "outcome", label: "Resultado", options: [["success", "Correcto"], ["failure", "Fallo"], ["denied", "Denegado"]] }],
    empty: { title: "Sin eventos", text: "No hay eventos que coincidan." },
    columns: [
      { key: "occurred_at", label: "Fecha", value: (e) => e.occurred_at, render: (e) => formatDate(e.occurred_at) },
      { key: "action", label: "Acción", className: "mono" },
      { key: "outcome", label: "Resultado", render: (e) => h("span", { class: `badge ${e.outcome === "success" ? "ok" : "bad"}` }, e.outcome) },
      { key: "target", label: "Objetivo", className: "mono", value: (e) => [e.target_type, e.target_id].filter(Boolean).join(":") },
      { key: "ip", label: "IP", className: "mono", value: (e) => e.ip ?? "" },
    ],
  });

  async function load() {
    const { events } = await api.adminAudit(action.input.value.trim());
    table.setRows(events);
  }
  const form = h(
    "form",
    { class: "inline-form", onsubmit: (event) => { event.preventDefault(); load().catch((error) => toast(error.message, { error: true })); } },
    action.element,
    h("button", { class: "button secondary", type: "submit" }, "Buscar"),
  );
  clear(panel).append(h("section", { class: "card" }, form), table.element);
  await load();
}

async function usagePanel(panel) {
  const { usage, month_cost_usd: cost } = await api.adminUsage();
  const table = dataTable({
    caption: "Uso por modelo",
    empty: { title: "Sin uso registrado", text: "Aparecerá aquí cuando se use el modelo." },
    columns: [
      { key: "provider", label: "Proveedor" },
      { key: "model", label: "Modelo", className: "mono" },
      { key: "status", label: "Estado" },
      { key: "requests", label: "Peticiones" },
      { key: "input_tokens", label: "Tokens entrada" },
      { key: "output_tokens", label: "Tokens salida" },
      { key: "cost_usd", label: "Coste (USD)", className: "mono", render: (u) => Number(u.cost_usd).toFixed(4) },
    ],
    rows: usage,
  });
  clear(panel).append(h("section", { class: "card" }, h("h2", {}, "Coste del mes (USD)"), h("p", { class: "metric mono" }, Number(cost ?? 0).toFixed(4))), table.element);
}
