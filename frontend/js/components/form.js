// Campo de formulario consistente: etiqueta visible, ayuda asociada y atributos de accesibilidad.
import { h } from "../dom.js";

export function field({ id, label, type = "text", options, hint, ...attributes }) {
  const control = options
    ? h("select", { id, ...attributes }, options.map(([value, text]) => h("option", { value, selected: value === attributes.value }, text)))
    : h("input", { id, type, ...attributes });
  const hintId = `${id}-hint`;
  if (hint) control.setAttribute("aria-describedby", hintId);
  return {
    input: control,
    element: h("div", { class: "field" }, h("label", { for: id }, label), control, hint ? h("span", { class: "hint", id: hintId }, hint) : null),
  };
}
