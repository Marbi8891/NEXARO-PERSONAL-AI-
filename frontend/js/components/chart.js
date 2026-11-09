// Gráfico de barras diarias en SVG. Una sola serie, un solo color (--accent), eje desde cero y
// alternativa textual: el resumen va en aria-label y la tabla completa en un <details>.
import { h } from "../dom.js";

const NS = "http://www.w3.org/2000/svg";
const W = 600;
const H = 160;
const PAD_TOP = 8;
const PAD_BOTTOM = 0;

function svg(tag, attrs = {}, ...children) {
  const node = document.createElementNS(NS, tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value));
  node.append(...children);
  return node;
}

const shortDate = (iso) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;

export function barChart({ data, valueKey, label, unit }) {
  const max = Math.max(1, ...data.map((d) => d[valueKey]));
  const total = data.reduce((sum, d) => sum + d[valueKey], 0);
  const slot = W / data.length;
  const plot = H - PAD_TOP - PAD_BOTTOM;

  const bars = data.map((d, i) => {
    const height = Math.round((d[valueKey] / max) * plot);
    const bar = svg("rect", { class: "bar", x: i * slot + slot * 0.15, y: PAD_TOP + plot - height, width: slot * 0.7, height, rx: 2 }, svg("title", {}, `${shortDate(d.date)}: ${d[valueKey]} ${unit}`));
    return bar;
  });
  const chart = svg(
    "svg",
    { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "none", role: "img", "aria-label": `${label}: ${total} ${unit} en ${data.length} días, máximo diario ${max}.`, class: "chart" },
    svg("line", { class: "baseline", x1: 0, x2: W, y1: PAD_TOP + plot, y2: PAD_TOP + plot }),
    ...bars,
  );

  const rows = data.map((d) => h("tr", {}, h("td", {}, d.date), h("td", {}, String(d[valueKey]))));
  return h(
    "figure",
    { class: "chart-figure" },
    h("figcaption", {}, label),
    chart,
    h("div", { class: "chart-axis", "aria-hidden": "true" }, h("span", {}, shortDate(data[0].date)), h("span", {}, shortDate(data[data.length - 1].date))),
    h("details", { class: "chart-data" }, h("summary", {}, "Ver datos"), h("table", { class: "table compact" }, h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Día"), h("th", { scope: "col" }, unit))), h("tbody", {}, rows))),
  );
}
