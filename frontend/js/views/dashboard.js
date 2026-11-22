// Panel: resumen real de actividad. Todo viene de /api/dashboard; si no hay datos se dice, no se simula.
import { api } from "../api.js";
import { barChart } from "../components/chart.js";
import { emptyState, errorState, loadingState } from "../components/states.js";
import { clear, formatDate, h } from "../dom.js";
import { getUser } from "../state.js";

const stat = (label, value, hint) => h("div", { class: "stat" }, h("dt", {}, label), h("dd", {}, String(value)), hint ? h("small", {}, hint) : null);

function personalSection(activity, days) {
  const chart = activity.messages
    ? barChart({ data: activity.daily, valueKey: "messages", label: `Mensajes por día (últimos ${days} días)`, unit: "mensajes" })
    : null;
  const recent = activity.recent.length
    ? h("ul", { class: "recent-list" }, activity.recent.map((c) => h("li", {}, h("a", { href: `#/chat/${encodeURIComponent(c.id)}` }, h("strong", {}, c.title ?? "Conversación vacía"), h("small", {}, formatDate(c.last_activity ?? c.created_at))))))
    : emptyState({ title: "Aún no hay conversaciones", text: "Empieza una en el chat y aparecerá aquí.", action: h("a", { class: "button", href: "#/chat" }, "Ir al chat") });
  return h(
    "section",
    { class: "card" },
    h("h2", {}, "Tu actividad · NEXARO Personal AI"),
    h("dl", { class: "stats" }, stat("Conversaciones", activity.conversations), stat("Mensajes", activity.messages), stat("Última actividad", activity.last_activity ? formatDate(activity.last_activity) : "—")),
    chart,
    h("h3", {}, "Conversaciones recientes"),
    recent,
  );
}

function adminSection(admin, days) {
  const { users, usage, security } = admin;
  return h(
    "section",
    { class: "card" },
    h("h2", {}, "Plataforma · solo administradores"),
    h("dl", { class: "stats" }, stat("Cuentas", users.total, `Pendientes: ${users.pending} · Inactivas: ${users.inactive}`), stat(`Peticiones al modelo (${days} d)`, usage.requests_period), stat("Coste del mes (USD)", usage.month_cost_usd.toFixed(4)), stat("Accesos fallidos (24 h)", security.failed_logins_24h), stat("Acciones denegadas (24 h)", security.denied_24h)),
    usage.requests_period ? barChart({ data: usage.daily, valueKey: "requests", label: `Peticiones al modelo por día (últimos ${days} días)`, unit: "peticiones" }) : h("p", { class: "hint" }, "Aún no se han registrado peticiones al modelo en este periodo."),
  );
}

export async function dashboardView({ container, shell }) {
  shell.setTitle("Panel");
  const body = h("div", { class: "page-body stack" });
  container.append(body);

  async function load() {
    clear(body).append(loadingState("Cargando resumen..."));
    try {
      const data = await api.dashboard();
      clear(body);
      body.append(personalSection(data.activity, data.days));
      if (data.admin && getUser().role === "admin") body.append(adminSection(data.admin, data.days));
    } catch {
      clear(body).append(errorState("No se pudo cargar el resumen.", { onRetry: load }));
    }
  }
  await load();
}
