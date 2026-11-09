// Módulo Security: resumen de seguridad derivado de la auditoría real. Solo administradores.
import { api } from "../api.js";
import { barChart } from "../components/chart.js";
import { field } from "../components/form.js";
import { emptyState, errorState, loadingState } from "../components/states.js";
import { dataTable } from "../components/table.js";
import { append, clear, formatDate, h } from "../dom.js";

const PERIODS = [["7", "7 días"], ["14", "14 días"], ["30", "30 días"], ["90", "90 días"]];
const OUTCOME = { failure: ["bad", "Fallo"], denied: ["warn", "Denegado"] };

const stat = (label, value, hint) => h("div", { class: "stat" }, h("dt", {}, label), h("dd", {}, String(value)), hint ? h("small", {}, hint) : null);

export async function securityView({ container, shell }) {
  shell.setTitle("Seguridad");
  const body = h("div", { class: "page-body stack" });
  const content = h("div", { class: "stack" });
  const period = field({ id: "sec-days", label: "Periodo", options: PERIODS, value: "14" });
  period.input.addEventListener("change", load);
  container.append(body);
  append(body, [h("section", { class: "card" }, h("p", { class: "hint" }, "Resumen calculado a partir de la auditoría real. La auditoría completa está en Administración."), period.element), content]);

  async function load() {
    clear(content).append(loadingState("Cargando resumen de seguridad..."));
    try {
      const data = await api.adminSecurity(Number(period.input.value));
      clear(content);
      const { totals } = data;
      const incidents = totals.failed_logins + totals.denied + totals.lockouts;
      append(content, [
        h("section", { class: "card" }, h("h2", {}, `Últimos ${data.days} días`), h("dl", { class: "stats" }, stat("Accesos fallidos", totals.failed_logins), stat("Acciones denegadas", totals.denied), stat("Bloqueos por intentos", totals.lockouts), stat("Accesos correctos", totals.successful_logins)),
          incidents === 0
            ? emptyState({ title: "Sin incidencias en el periodo", text: "No hay accesos fallidos, denegaciones ni bloqueos registrados." })
            : [
                totals.failed_logins ? barChart({ data: data.daily, valueKey: "failed_logins", label: "Accesos fallidos por día", unit: "fallos" }) : null,
                totals.denied ? barChart({ data: data.daily, valueKey: "denied", label: "Acciones denegadas por día", unit: "denegaciones" }) : null,
              ]),
        dataTable({
          caption: "Orígenes con más accesos fallidos",
          rows: data.top_ips,
          empty: { title: "Sin accesos fallidos", text: "Ninguna dirección ha fallado un acceso en el periodo." },
          columns: [{ key: "ip", label: "Dirección IP", className: "mono" }, { key: "failed_logins", label: "Fallos" }],
        }).element,
        dataTable({
          caption: "Incidencias por tipo",
          rows: data.by_action,
          empty: { title: "Sin incidencias" },
          columns: [
            { key: "action", label: "Acción", className: "mono" },
            { key: "outcome", label: "Resultado", value: (r) => OUTCOME[r.outcome]?.[1] ?? r.outcome, render: (r) => h("span", { class: `badge ${OUTCOME[r.outcome]?.[0] ?? ""}` }, OUTCOME[r.outcome]?.[1] ?? r.outcome) },
            { key: "count", label: "Eventos" },
          ],
        }).element,
        dataTable({
          caption: "Últimas incidencias",
          rows: data.recent,
          empty: { title: "Sin incidencias recientes" },
          columns: [
            { key: "occurred_at", label: "Fecha (UTC)", value: (e) => formatDate(e.occurred_at) },
            { key: "action", label: "Acción", className: "mono" },
            { key: "outcome", label: "Resultado", value: (e) => OUTCOME[e.outcome]?.[1] ?? e.outcome, render: (e) => h("span", { class: `badge ${OUTCOME[e.outcome]?.[0] ?? ""}` }, OUTCOME[e.outcome]?.[1] ?? e.outcome) },
            { key: "ip", label: "IP", value: (e) => e.ip ?? "—", className: "mono" },
          ],
        }).element,
      ]);
    } catch (error) {
      clear(content).append(errorState(error.message, { onRetry: load }));
    }
  }
  await load();
}
