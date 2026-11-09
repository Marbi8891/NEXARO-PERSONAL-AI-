// Markdown mínimo y seguro: se construye con nodos DOM (nunca innerHTML), de modo que el HTML que
// devuelva el modelo se ve como texto. Soporta bloques de código, listas, títulos, negrita,
// cursiva y código en línea. No genera enlaces ni imágenes a propósito.
import { h } from "./dom.js";

const INLINE = /(`[^`\n]+`|\*\*[^*\n]+\*\*|\*[^*\s][^*\n]*\*)/g;

export function renderInline(text) {
  const nodes = [];
  let last = 0;
  for (const match of text.matchAll(INLINE)) {
    if (match.index > last) nodes.push(text.slice(last, match.index));
    const token = match[0];
    if (token.startsWith("`")) nodes.push(h("code", { class: "inline-code" }, token.slice(1, -1)));
    else if (token.startsWith("**")) nodes.push(h("strong", {}, token.slice(2, -2)));
    else nodes.push(h("em", {}, token.slice(1, -1)));
    last = match.index + token.length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

function paragraph(lines) {
  const children = [];
  lines.forEach((line, index) => {
    if (index) children.push(h("br"));
    children.push(...renderInline(line));
  });
  return h("p", {}, children);
}

// Un bloque de código sin cerrar (streaming en curso) se muestra ya como código.
export function renderMarkdown(source) {
  const blocks = [];
  const lines = String(source).replace(/\r\n?/g, "\n").split("\n");
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    const fence = line.match(/^\s*```\s*([\w+#.-]*)\s*$/);
    if (fence) {
      const body = [];
      index += 1;
      while (index < lines.length && !/^\s*```\s*$/.test(lines[index])) body.push(lines[index++]);
      index += 1; // cierre
      const attrs = fence[1] ? { "data-lang": fence[1] } : {};
      blocks.push(h("pre", { class: "code-block", ...attrs }, h("code", {}, body.join("\n"))));
      continue;
    }
    if (!line.trim()) {
      index += 1;
      continue;
    }
    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    if (heading) {
      blocks.push(h(`h${Math.min(heading[1].length + 2, 6)}`, { class: "md-heading" }, renderInline(heading[2])));
      index += 1;
      continue;
    }
    const item = line.match(/^\s*([-*]|\d+[.)])\s+(.*)$/);
    if (item) {
      const ordered = /\d/.test(item[1]);
      const items = [];
      while (index < lines.length) {
        const current = lines[index].match(/^\s*([-*]|\d+[.)])\s+(.*)$/);
        if (!current || /\d/.test(current[1]) !== ordered) break;
        items.push(h("li", {}, renderInline(current[2])));
        index += 1;
      }
      blocks.push(h(ordered ? "ol" : "ul", {}, items));
      continue;
    }
    const para = [];
    while (index < lines.length && lines[index].trim() && !/^\s*```/.test(lines[index]) && !/^(#{1,4}\s|\s*([-*]|\d+[.)])\s)/.test(lines[index])) {
      para.push(lines[index++]);
    }
    blocks.push(paragraph(para));
  }
  return blocks;
}
