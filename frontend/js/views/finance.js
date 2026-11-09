// Módulo Finance: gastos de una organización (resumen mensual, alta/edición, exportación CSV).
// Solo propietarios y administradores (lo impone el servidor). Importes: céntimos en la API.
import { api } from "../api.js";
import { barChart } from "../components/chart.js";
import { confirmDialog } from "../components/dialog.js";
import { field } from "../components/form.js";
import { emptyState, errorState, loadingState } from "../components/states.js";
import { dataTable } from "../components/table.js";
import { toast } from "../components/toast.js";
import { append, clear, h } from "../dom.js";

const canUse = (org) => org.role === "owner" || org.role === "admin";
const euros = (cents) => new Intl.NumberFormat("es-ES", { style: "currency", currency: "EUR" }).format(cents / 100);
const stat = (label, value, hint) => h("div", { class: "stat" }, h("dt", {}, label), h("dd", {}, String(value)), hint ? h("small", {}, hint) : null);
const monthLabel = (ym) => new Date(`${ym}-01T12:00:00`).toLocaleDateString("es-ES", { month: "short" });
const today = () => new Date().toISOString().slice(0, 10);

// «12,50» o «12.5» → 1250. Sin separador de miles: «1.234,56» se rechaza en vez de adivinar.
export function parseEuros(text) {
  const match = /^(\d+)(?:[.,](\d{1,2}))?$/.exec(text.trim());
  if (!match) return null;
  return Number(match[1]) * 100 + Number((match[2] ?? "").padEnd(2, "0") || 0);
}
const toInput = (cents) => `${Math.floor(cents / 100)},${String(cents % 100).padStart(2, "0")}`;

export async function financeView({ container, shell }) {
  shell.setTitle("Finanzas");
  const body = h("div", { class: "page-body stack" });
  container.append(body);

  let organizations;
  try {
    organizations = (await api.organizations()).organizations.filter(canUse);
  } catch (error) {
    body.append(errorState(error.message));
    return;
  }
  if (organizations.length === 0) {
    body.append(
      emptyState({
        title: "Sin acceso a finanzas",
        text: "Los gastos los gestionan los propietarios y administradores de una organización. Pide a uno de ellos que te añada con ese rol.",
        action: h("a", { class: "button secondary", href: "#/organizations" }, "Ver organizaciones"),
      }),
    );
    return;
  }

  let formRef = null; // el formulario activo; la tabla le pide cargar un gasto para editarlo
  const content = h("div", { class: "stack" });
  const picker = field({ id: "fin-org", label: "Organización", options: organizations.map((o) => [o.id, o.name]), value: organizations[0].id });
  const month = field({ id: "fin-month", label: "Mes", type: "month", value: today().slice(0, 7) });
  const current = () => organizations.find((o) => o.id === picker.input.value);
  const reload = () => show(current());
  picker.input.addEventListener("change", reload);
  month.input.addEventListener("change", () => month.input.value && reload());
  append(body, [h("section", { class: "card" }, h("div", { class: "inline-form" }, organizations.length > 1 ? picker.element : null, month.element)), content]);
  await show(organizations[0]);

  async function show(org) {
    const ym = month.input.value || today().slice(0, 7);
    const last = new Date(Number(ym.slice(0, 4)), Number(ym.slice(5, 7)), 0).getDate();
    const range = `start=${ym}-01&end=${ym}-${String(last).padStart(2, "0")}`;
    clear(content).append(loadingState());
    try {
      const [summary, list] = await Promise.all([api.expenseSummary(org.id, ym), api.expenses(org.id, `${range}&limit=200`)]);
      append(clear(content), [
        h("section", { class: "card" }, h("h2", {}, `Resumen de ${ym}`), h("dl", { class: "stats" }, stat("Gasto del mes", euros(summary.total_cents)), stat("IVA incluido", euros(summary.vat_cents)), stat("Nº de gastos", summary.count)),
          summary.history.some((m) => m.total_cents > 0) ? barChart({ data: summary.history, valueKey: "total_cents", label: "Gasto por mes", unit: "€", labelKey: "month", formatLabel: monthLabel, formatValue: euros, periodNoun: "meses", maxWord: "mensual", keyHeader: "Mes" }) : null),
        summary.by_category.length ? categoryTable(summary) : null,
        expenseForm(org, list.categories, reload),
        expenseTable(org, list, range, reload),
      ]);
    } catch (error) {
      clear(content).append(errorState(error.message, { onRetry: () => show(org) }));
    }
  }

  function categoryTable(summary) {
    return dataTable({
      caption: "Por categoría",
      rows: summary.by_category,
      initialSort: null,
      columns: [
        { key: "category", label: "Categoría" },
        { key: "count", label: "Gastos" },
        { key: "total_cents", label: "Total", search: false, render: (c) => euros(c.total_cents) },
      ],
    }).element;
  }

  function expenseForm(org, categories, done) {
    let editingId = null;
    const date = field({ id: "exp-date", label: "Fecha", type: "date", required: true, value: today(), max: today() });
    const description = field({ id: "exp-desc", label: "Descripción", required: true, maxlength: "200" });
    const vendor = field({ id: "exp-vendor", label: "Proveedor", maxlength: "120" });
    const category = field({ id: "exp-cat", label: "Categoría", required: true, maxlength: "40", list: "exp-categories" });
    const amount = field({ id: "exp-amount", label: "Importe total (€)", required: true, inputmode: "decimal", hint: "Con IVA. Ejemplo: 12,50" });
    const vat = field({ id: "exp-vat", label: "De ello, IVA (€)", inputmode: "decimal", value: "0" });
    const submit = h("button", { class: "button", type: "submit" }, "Añadir gasto");
    const cancel = h("button", { class: "button secondary", type: "button", hidden: true, onclick: () => done() }, "Cancelar edición");
    const heading = h("h2", {}, "Nuevo gasto");

    const form = h(
      "form",
      {
        class: "inline-form",
        id: "expense-form",
        onsubmit: async (event) => {
          event.preventDefault();
          const total = parseEuros(amount.input.value);
          const vatCents = vat.input.value.trim() === "" ? 0 : parseEuros(vat.input.value);
          if (total === null || vatCents === null) return toast("Importe no válido. Usa números con coma o punto, sin separador de miles (12,50).", { error: true });
          const payload = { spent_on: date.input.value, description: description.input.value.trim(), vendor: vendor.input.value.trim() || null, category: category.input.value.trim(), amount_cents: total, vat_cents: vatCents };
          try {
            if (editingId) await api.updateExpense(org.id, editingId, payload);
            else await api.createExpense(org.id, payload);
            toast(editingId ? "Gasto actualizado." : "Gasto añadido.");
            await done();
          } catch (error) {
            toast(error.message, { error: true });
          }
        },
      },
      date.element, description.element, vendor.element, category.element, amount.element, vat.element, submit, cancel,
      h("datalist", { id: "exp-categories" }, categories.map((c) => h("option", { value: c }))),
    );
    // La tabla llama a esto para cargar un gasto en el formulario.
    form.edit = (e) => {
      editingId = e.id;
      date.input.value = e.spent_on;
      description.input.value = e.description;
      vendor.input.value = e.vendor ?? "";
      category.input.value = e.category;
      amount.input.value = toInput(e.amount_cents);
      vat.input.value = toInput(e.vat_cents);
      submit.textContent = "Guardar cambios";
      cancel.hidden = false;
      heading.textContent = "Editar gasto";
      description.input.focus();
      form.scrollIntoView?.({ block: "center" });
    };
    formRef = form;
    return h("section", { class: "card" }, heading, form);
  }

  function expenseTable(org, list, range, done) {
    const table = dataTable({
      caption: `Gastos (${list.total}) · total ${euros(list.total_cents)}`,
      rows: list.expenses,
      empty: { title: "Sin gastos este mes", text: "Añade el primero con el formulario de arriba." },
      initialSort: null,
      columns: [
        { key: "spent_on", label: "Fecha" },
        { key: "description", label: "Descripción" },
        { key: "vendor", label: "Proveedor", value: (e) => e.vendor ?? "—" },
        { key: "category", label: "Categoría" },
        { key: "amount_cents", label: "Importe", search: false, render: (e) => euros(e.amount_cents) },
        { key: "vat_cents", label: "IVA", search: false, render: (e) => euros(e.vat_cents) },
        {
          key: "actions", label: "Acciones", sortable: false, search: false, className: "actions",
          render: (e) => h("span", { class: "row-actions" },
            h("button", { class: "button secondary small", type: "button", "aria-label": `Editar ${e.description}`, onclick: () => formRef?.edit(e) }, "Editar"),
            h("button", { class: "button danger small", type: "button", "aria-label": `Borrar ${e.description}`, onclick: async () => {
              if (!(await confirmDialog({ title: "¿Borrar gasto?", message: `«${e.description}» (${euros(e.amount_cents)}) dejará de contar en los resúmenes.`, confirmLabel: "Borrar", danger: true }))) return;
              try {
                await api.deleteExpense(org.id, e.id);
                toast("Gasto borrado.");
                await done();
              } catch (error) {
                toast(error.message, { error: true });
              }
            } }, "Borrar")),
        },
      ],
    });
    return h("div", { class: "stack" }, table.element, h("p", {}, h("a", { class: "button secondary", href: `/api/organizations/${encodeURIComponent(org.id)}/expenses/export.csv?${range}`, download: "gastos.csv" }, "Exportar este mes (CSV)")));
  }
}
