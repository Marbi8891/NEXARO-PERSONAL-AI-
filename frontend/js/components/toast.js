// Avisos efímeros accesibles. Los de éxito se cierran solos; los de error esperan a que se lean.
import { h } from "../dom.js";

const SUCCESS_MS = 5000;
let region = null;

function container() {
  if (!region?.isConnected) {
    region = h("div", { class: "toasts", "aria-live": "polite" });
    document.body.append(region);
  }
  return region;
}

export function toast(message, { error = false } = {}) {
  const node = h(
    "div",
    { class: error ? "toast error" : "toast", role: error ? "alert" : "status" },
    h("span", {}, message),
    h("button", { class: "toast-close", type: "button", "aria-label": "Cerrar aviso", onclick: () => node.remove() }, "×"),
  );
  container().append(node);
  if (!error) setTimeout(() => node.remove(), SUCCESS_MS);
}
