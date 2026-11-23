import { api } from "../api.js";
import { field } from "../components/form.js";
import { toast } from "../components/toast.js";
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

  // Cambio de contraseña: exige la actual; el servidor cierra las demás sesiones.
  const currentPw = field({ id: "pw-current", label: "Contraseña actual", type: "password", required: true, autocomplete: "current-password" });
  const newPw = field({ id: "pw-new", label: "Contraseña nueva", type: "password", required: true, minlength: "12", autocomplete: "new-password", hint: "Mínimo 12 caracteres." });
  const repeatPw = field({ id: "pw-repeat", label: "Repite la contraseña nueva", type: "password", required: true, minlength: "12", autocomplete: "new-password" });
  const pwError = h("p", { class: "form-error", role: "alert" });
  const pwForm = h(
    "form",
    {
      class: "stack",
      onsubmit: async (event) => {
        event.preventDefault();
        pwError.textContent = "";
        if (newPw.input.value !== repeatPw.input.value) {
          pwError.textContent = "Las contraseñas nuevas no coinciden.";
          return;
        }
        try {
          const result = await api.changePassword(currentPw.input.value, newPw.input.value);
          event.target.reset();
          toast(result.other_sessions_revoked ? `Contraseña cambiada. Se cerraron ${result.other_sessions_revoked} sesiones en otros dispositivos.` : "Contraseña cambiada.");
        } catch (error) {
          pwError.textContent = error.message;
        }
      },
    },
    currentPw.element,
    newPw.element,
    repeatPw.element,
    pwError,
    h("button", { class: "button", type: "submit" }, "Cambiar contraseña"),
  );

  container.append(
    h(
      "div",
      { class: "page-body stack" },
      h("section", { class: "card" }, h("h2", {}, "Cuenta"), h("dl", { class: "details" }, h("dt", {}, "Correo"), h("dd", {}, user.email), h("dt", {}, "Rol"), h("dd", {}, user.role === "admin" ? "Administrador de la plataforma" : "Usuario"))),
      h("section", { class: "card" }, h("h2", {}, "Apariencia"), h("fieldset", { class: "choices" }, h("legend", {}, "Tema de color"), themes), h("p", { class: "hint" }, "«Sistema» sigue la preferencia de tu dispositivo. Se guarda solo en este navegador.")),
      h("section", { class: "card" }, h("h2", {}, "Contraseña"), pwForm),
      h("section", { class: "card" }, h("h2", {}, "Sesión"), h("p", { class: "hint" }, "Cierra la sesión en este dispositivo."), h("button", { class: "button secondary", type: "button", onclick: shell.logout }, "Cerrar sesión")),
    ),
  );
}
