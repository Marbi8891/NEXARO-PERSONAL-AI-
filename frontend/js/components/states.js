// Estados de pantalla unificados: cargando, vacío y error. Siempre con texto, nunca solo icono.
import { h } from "../dom.js";

export function loadingState(text = "Cargando...") {
  return h("div", { class: "state", role: "status" }, h("span", { class: "spinner", "aria-hidden": "true" }), text);
}

export function emptyState({ title, text, action }) {
  return h("div", { class: "state empty-state" }, h("h3", {}, title), text ? h("p", {}, text) : null, action ?? null);
}

export function errorState(message, { onRetry } = {}) {
  return h(
    "div",
    { class: "state error-state", role: "alert" },
    h("p", {}, message),
    onRetry ? h("button", { class: "button secondary small", type: "button", onclick: onRetry }, "Reintentar") : null,
  );
}
