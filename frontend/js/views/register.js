import { api } from "../api.js";
import { brand } from "../components/brand.js";
import { field } from "../components/form.js";
import { clear, h } from "../dom.js";

export function registerView({ container }) {
  document.title = "Solicitar acceso · NEXARO";
  const error = h("div", { class: "form-error", role: "alert" });
  const email = field({ id: "email", label: "Correo electrónico", type: "email", autocomplete: "username", required: true });
  const password = field({ id: "password", label: "Contraseña", type: "password", autocomplete: "new-password", required: true, minlength: "12", hint: "Mínimo 12 caracteres." });
  const submit = h("button", { class: "button", type: "submit" }, "Solicitar acceso");
  const card = h("form", { class: "auth-card" });

  async function onSubmit(event) {
    event.preventDefault();
    error.textContent = "";
    submit.disabled = true;
    try {
      await api.register(email.input.value.trim(), password.input.value);
      clear(card).append(
        brand(),
        h("h1", {}, "Solicitud enviada"),
        h("p", { class: "form-ok", role: "status" }, "Un administrador debe aprobar tu cuenta antes de que puedas entrar."),
        h("p", { class: "auth-alt" }, h("a", { href: "#/login" }, "Volver al acceso")),
      );
    } catch (failure) {
      error.textContent = failure.status === 403 ? "El registro está cerrado. Pide a un administrador que cree tu cuenta." : failure.message;
      submit.disabled = false;
    }
  }

  card.addEventListener("submit", onSubmit);
  card.append(brand(), h("h1", {}, "Solicitar acceso"), email.element, password.element, error, submit, h("p", { class: "auth-alt" }, h("a", { href: "#/login" }, "Ya tengo cuenta")));
  container.append(h("main", { class: "auth" }, card));
  email.input.focus();
}
