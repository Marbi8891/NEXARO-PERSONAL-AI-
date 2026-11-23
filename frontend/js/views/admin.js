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
    ["models", "Modelos", modelsPanel],
    ["usage", "Uso del modelo", usagePanel],
    ["ops", "Operaciones", opsPanel],
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
  const { usage, month_cost_usd: cost, inference = [] } = await api.adminUsage();
  const ms = (value) => (value === null || value === undefined ? "—" : `${Math.round(value)} ms`);
  const speed = dataTable({
    caption: "Rendimiento de inferencia (medias de los últimos días)",
    empty: { title: "Sin métricas todavía", text: "Se registran con las respuestas en streaming." },
    search: false,
    columns: [
      { key: "model", label: "Modelo", className: "mono" },
      { key: "requests", label: "Peticiones" },
      { key: "avg_ttft_ms", label: "Primer token", render: (r) => ms(r.avg_ttft_ms) },
      { key: "avg_load_ms", label: "Carga del modelo", render: (r) => ms(r.avg_load_ms) },
      { key: "avg_prompt_eval_ms", label: "Lectura del prompt", render: (r) => ms(r.avg_prompt_eval_ms) },
      { key: "avg_total_ms", label: "Total", render: (r) => ms(r.avg_total_ms) },
      { key: "avg_tokens_per_second", label: "Tokens/s", render: (r) => (r.avg_tokens_per_second ?? "—") },
      { key: "cold_loads", label: "Cargas en frío" },
    ],
    rows: inference,
  });
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
  clear(panel).append(h("section", { class: "card" }, h("h2", {}, "Coste del mes (USD)"), h("p", { class: "metric mono" }, Number(cost ?? 0).toFixed(4))), table.element, speed.element);
}

const CIRCUIT = { closed: "Normal", open: "En pausa", half_open: "Probando" };

async function modelsPanel(panel) {
  const { routes } = await api.adminModels();
  const gb = (bytes) => (typeof bytes === "number" ? `${(bytes / 1e9).toFixed(1)} GB` : "—");
  const status = dataTable({
    caption: "Rutas del gateway",
    empty: { title: "Sin rutas", text: "El gateway no está configurado." },
    search: false,
    columns: [
      { key: "provider", label: "Proveedor" },
      { key: "model", label: "Modelo", className: "mono" },
      { key: "cloud", label: "Ubicación", value: (r) => (r.cloud ? "Nube" : "Local") },
      { key: "healthy", label: "Estado", render: (r) => h("span", { class: `badge ${r.healthy ? "ok" : "bad"}` }, r.healthy ? "Disponible" : "No disponible") },
      { key: "model_installed", label: "Modelo instalado", value: (r) => (r.model_installed === null ? "—" : r.model_installed ? "Sí" : "No") },
      { key: "circuit", label: "Cortacircuitos", value: (r) => CIRCUIT[r.circuit] ?? r.circuit },
      { key: "consecutive_failures", label: "Fallos seguidos" },
    ],
    rows: routes,
  });
  const installed = dataTable({
    caption: "Modelos instalados en Ollama",
    empty: { title: "Sin datos", text: "Ollama no responde o no hay modelos instalados." },
    search: false,
    columns: [
      { key: "name", label: "Modelo", className: "mono" },
      { key: "parameter_size", label: "Parámetros", value: (m) => m.parameter_size ?? "—" },
      { key: "quantization", label: "Cuantización", value: (m) => m.quantization ?? "—" },
      { key: "size_bytes", label: "Tamaño", value: (m) => gb(m.size_bytes) },
    ],
    rows: routes.flatMap((r) => r.installed_models ?? []),
  });
  clear(panel).append(status.element, installed.element);
}

// Panel de operaciones (OPERATIONS.md): estado real de cada componente; "—" si un dato no existe.
const opsStat = (label, value, hint) => h("div", { class: "stat" }, h("dt", {}, label), h("dd", {}, value ?? "—"), hint ? h("small", {}, hint) : null);
const opsBadge = (good, text, warn = false) => h("span", { class: `badge ${good ? "ok" : warn ? "warn" : "bad"}` }, text);
const bytes = (n) => (typeof n === "number" ? (n >= 1e9 ? `${(n / 1e9).toFixed(1)} GB` : `${(n / 1e6).toFixed(1)} MB`) : "—");
const BACKUP = { ok: [true, "Al día"], stale: [false, "Antigua", true], failed: [false, "Falló"], never: [false, "Ninguna", true], not_configured: [false, "Sin configurar", true], unreadable: [false, "Ilegible"] };

async function opsPanel(panel) {
  const s = await api.adminStatus();
  const { cpu, memory, disk } = s.system;
  const backup = BACKUP[s.backups.status] ?? [false, s.backups.status];
  const lat = s.requests.latency_ms;
  const summary = h(
    "section",
    { class: "card" },
    h("h2", {}, "Estado de los servicios"),
    h(
      "dl",
      { class: "stats" },
      opsStat("Backend", opsBadge(true, "En marcha"), `Activo ${Math.round(s.requests.uptime_seconds / 60)} min`),
      opsStat("Ollama", opsBadge(s.ollama.status === "ok", s.ollama.status === "ok" ? "Conectado" : "Sin conexión"), s.ollama.model),
      opsStat("Modelo", opsBadge(s.ollama.model_ready === true, s.ollama.model_ready === false ? "No instalado" : s.ollama.model_ready ? "Listo" : "Desconocido", s.ollama.model_ready === null)),
      opsStat("Base de datos", opsBadge(s.database.status === "ok", s.database.status === "ok" ? "Íntegra" : s.database.status), `Esquema v${s.database.schema_version ?? "?"} · ${bytes(s.database.size_bytes)}`),
      opsStat("Agentes", String(s.agents.length), s.agents.map((a) => a.id).join(", ")),
      opsStat("Copia de seguridad", opsBadge(backup[0], backup[1], backup[2]), s.backups.finished_at ? `${formatDate(s.backups.finished_at)} · ${s.backups.age_hours ?? "?"} h` : "Programa scripts/backup_nexaro.ps1"),
    ),
  );
  const resources = h(
    "section",
    { class: "card" },
    h("h2", {}, "Recursos y peticiones"),
    h(
      "dl",
      { class: "stats" },
      opsStat("CPU (carga 1 min)", cpu.load_1m === null ? "—" : String(cpu.load_1m), cpu.cpu_quota ? `Límite: ${cpu.cpu_quota} CPU` : `${cpu.cpus_visible ?? "?"} CPU visibles`),
      opsStat("Memoria del backend", memory.percent === null ? bytes(memory.process_rss_bytes) : `${memory.percent} %`, memory.container_limit_bytes ? `de ${bytes(memory.container_limit_bytes)}` : null),
      opsStat("Disco de datos", disk.percent_used === null ? "—" : `${disk.percent_used} %`, `Libre: ${bytes(disk.free_bytes)}`),
      opsStat("Peticiones", String(s.requests.requests_total), `5xx: ${s.requests.requests_by_class["5xx"]} · 4xx: ${s.requests.requests_by_class["4xx"]}`),
      opsStat("Latencia API p50 / p95", lat.p50 === null ? "—" : `${lat.p50} / ${lat.p95} ms`, `${lat.samples} muestras`),
    ),
  );
  const generation = dataTable({
    caption: "Generación (últimas 24 h)",
    empty: { title: "Sin generaciones", text: "Aparecerán cuando se use el modelo." },
    search: false,
    columns: [
      { key: "model", label: "Modelo", className: "mono" },
      { key: "requests", label: "Peticiones" },
      { key: "avg_ttft_ms", label: "Primer token (ms)", value: (r) => r.avg_ttft_ms ?? "—" },
      { key: "avg_total_ms", label: "Total (ms)", value: (r) => r.avg_total_ms ?? "—" },
      { key: "avg_tokens_per_second", label: "Tokens/s", value: (r) => r.avg_tokens_per_second ?? "—" },
    ],
    rows: s.generation_last_24h,
  });
  const errors = dataTable({
    caption: "Errores recientes del servidor (5xx)",
    empty: { title: "Sin errores", text: "No ha habido errores 5xx desde el último arranque." },
    search: false,
    columns: [
      { key: "ts", label: "Hora", value: (e) => formatDate(e.ts) },
      { key: "method", label: "Método" },
      { key: "path", label: "Ruta", className: "mono" },
      { key: "status", label: "Estado" },
      { key: "request_id", label: "ID de petición", className: "mono" },
    ],
    rows: s.requests.recent_errors,
  });
  const refresh = h("button", { class: "button secondary small", type: "button", onclick: () => opsPanel(panel).catch((e) => toast(e.message, { error: true })) }, "Actualizar");
  clear(panel).append(h("div", { class: "stack" }, refresh, summary, resources, generation.element, errors.element));
}
