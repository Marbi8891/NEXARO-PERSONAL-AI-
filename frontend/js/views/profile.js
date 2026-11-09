import { h } from "../dom.js";
import { LABELS, getTheme, setTheme } from "../theme.js";
import { getUser } from "../state.js";

export function profileView({ container, shell }) {
  shell.setTitle("Perfil");
  const user = getUser();
  const current = getTheme();
  const themes = Object.entries(LABELS).map(([value, label]) =>
    h("label", { class: "choice" }, h("input", { type: "radio", name: "theme", value, checked: value === current, onchange: () => setTheme(value) }), label),
  );

  container.append(
    h(
      "div",
      { class: "page-body stack" },
      h("section", { class: "card" }, h("h2", {}, "Cuenta"), h("dl", { class: "details" }, h("dt", {}, "Correo"), h("dd", {}, user.email), h("dt", {}, "Rol"), h("dd", {}, user.role === "admin" ? "Administrador de la plataforma" : "Usuario"))),
      h("section", { class: "card" }, h("h2", {}, "Apariencia"), h("fieldset", { class: "choices" }, h("legend", {}, "Tema de color"), themes), h("p", { class: "hint" }, "«Sistema» sigue la preferencia de tu dispositivo. Se guarda solo en este navegador.")),
      h("section", { class: "card" }, h("h2", {}, "Sesión"), h("p", { class: "hint" }, "Cierra la sesión en este dispositivo."), h("button", { class: "button secondary", type: "button", onclick: shell.logout }, "Cerrar sesión")),
    ),
  );
}
