// Tabla de datos accesible con búsqueda, filtros, orden y paginación en el cliente.
// Pensada para conjuntos pequeños (cientos de filas); el servidor ya limita cada consulta.
import { append, clear, h } from "../dom.js";
import { emptyState } from "./states.js";

const PAGE_SIZES = [10, 25, 50];

function compare(a, b) {
  if (typeof a === "number" && typeof b === "number") return a - b;
  return String(a ?? "").localeCompare(String(b ?? ""), "es", { numeric: true, sensitivity: "base" });
}

/**
 * columns: [{ key, label, value?(row), render?(row), sortable? = true, search? = true }]
 * filters: [{ key, label, options: [[valor, texto]], match?(row, valor) }]
 */
export function dataTable({ caption, columns, rows = [], pageSize = 10, filters = [], searchLabel = "Buscar", empty, initialSort = null }) {
  let data = rows;
  let query = "";
  let page = 0;
  let size = pageSize;
  let sort = initialSort; // { key, dir: 1 | -1 }
  const chosen = {};

  const valueOf = (column, row) => (column.value ? column.value(row) : row[column.key]);

  const search = h("input", { id: `${caption}-search`.replace(/\W+/g, "-"), type: "search", placeholder: "Texto...", oninput: (event) => { query = event.target.value.trim().toLowerCase(); page = 0; draw(); } });
  const filterControls = filters.map((filter) => {
    const id = `${caption}-${filter.key}`.replace(/\W+/g, "-");
    const select = h("select", { id, onchange: (event) => { chosen[filter.key] = event.target.value; page = 0; draw(); } }, h("option", { value: "" }, "Todos"), filter.options.map(([value, text]) => h("option", { value }, text)));
    return h("div", { class: "toolbar-item" }, h("label", { for: id }, filter.label), select);
  });
  const sizeSelect = h("select", { id: `${caption}-size`.replace(/\W+/g, "-"), onchange: (event) => { size = Number(event.target.value); page = 0; draw(); } }, PAGE_SIZES.map((n) => h("option", { value: n, selected: n === size }, String(n))));
  const toolbar = h("div", { class: "toolbar" }, h("div", { class: "toolbar-item grow" }, h("label", { for: search.id }, searchLabel), search), filterControls, h("div", { class: "toolbar-item" }, h("label", { for: sizeSelect.id }, "Filas"), sizeSelect));

  const region = h("div", {});
  const element = h("section", { class: "data-table" }, toolbar, region);

  function visibleRows() {
    let result = data.filter((row) => {
      for (const filter of filters) {
        const value = chosen[filter.key];
        if (value && !(filter.match ? filter.match(row, value) : String(row[filter.key]) === value)) return false;
      }
      if (!query) return true;
      return columns.some((column) => column.search !== false && String(valueOf(column, row) ?? "").toLowerCase().includes(query));
    });
    if (sort) {
      const column = columns.find((c) => c.key === sort.key);
      result = [...result].sort((a, b) => sort.dir * compare(valueOf(column, a), valueOf(column, b)));
    }
    return result;
  }

  function sortBy(key) {
    sort = sort?.key === key ? { key, dir: -sort.dir } : { key, dir: 1 };
    page = 0;
    draw();
  }

  function draw() {
    clear(region);
    if (!data.length) {
      region.append(emptyState(empty ?? { title: "Sin datos", text: "Todavía no hay elementos." }));
      return;
    }
    const matches = visibleRows();
    const pages = Math.max(1, Math.ceil(matches.length / size));
    page = Math.min(page, pages - 1);
    const slice = matches.slice(page * size, page * size + size);

    const head = h("tr", {}, columns.map((column) => {
      const active = sort?.key === column.key;
      const header = h("th", { scope: "col", "aria-sort": active ? (sort.dir === 1 ? "ascending" : "descending") : null });
      if (column.sortable === false) header.append(column.label);
      else header.append(h("button", { class: "th-button", type: "button", onclick: () => sortBy(column.key) }, column.label, h("span", { "aria-hidden": "true" }, active ? (sort.dir === 1 ? " ▲" : " ▼") : "")));
      return header;
    }));
    const body = slice.map((row) => h("tr", {}, columns.map((column) => h("td", { class: column.className }, column.render ? column.render(row) : String(valueOf(column, row) ?? ""))))); 

    // append() de dom.js ignora null; el nativo lo escribiría como el texto "null".
    append(region, [
      h("div", { class: "table-wrap" }, h("table", {}, h("caption", {}, caption), h("thead", {}, head), h("tbody", {}, body))),
      matches.length ? null : emptyState({ title: "Ningún resultado", text: "Prueba con otro texto o quita los filtros." }),
      h(
        "div",
        { class: "table-footer" },
        h("p", { class: "table-status", role: "status", "aria-live": "polite" }, matches.length ? `${page * size + 1}–${page * size + slice.length} de ${matches.length}` : "0 resultados"),
        h("div", { class: "pager" },
          h("button", { class: "button secondary small", type: "button", disabled: page === 0, onclick: () => { page -= 1; draw(); } }, "Anterior"),
          h("span", {}, `Página ${page + 1} de ${pages}`),
          h("button", { class: "button secondary small", type: "button", disabled: page >= pages - 1, onclick: () => { page += 1; draw(); } }, "Siguiente"),
        ),
      ),
    ]);
  }

  draw();
  return {
    element,
    setRows(next) {
      data = next;
      draw();
    },
  };
}
