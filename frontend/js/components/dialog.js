// Confirmación modal sobre <dialog> nativo: gestiona foco, Escape y capa modal sin código propio.
import { h } from "../dom.js";

export function confirmDialog({ title, message, confirmLabel = "Confirmar", danger = false }) {
  return new Promise((resolve) => {
    const cancel = h("button", { class: "button secondary", type: "button", onclick: () => close(false) }, "Cancelar");
    const confirm = h("button", { class: danger ? "button danger" : "button", type: "button", onclick: () => close(true) }, confirmLabel);
    const dialog = h(
      "dialog",
      { class: "dialog", "aria-labelledby": "dialog-title", "aria-describedby": "dialog-text" },
      h("h2", { id: "dialog-title" }, title),
      h("p", { id: "dialog-text" }, message),
      h("div", { class: "dialog-actions" }, cancel, confirm),
    );
    let answer = false;
    function close(value) {
      answer = value;
      if (typeof dialog.close === "function") dialog.close();
      else finish();
    }
    function finish() {
      dialog.remove();
      resolve(answer);
    }
    dialog.addEventListener("close", finish); // también cubre Escape
    document.body.append(dialog);
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
    cancel.focus(); // la opción segura recibe el foco
  });
}
