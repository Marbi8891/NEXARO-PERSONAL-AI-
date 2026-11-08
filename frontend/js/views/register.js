import { api } from "../api.js";
import { brand } from "../components/brand.js";
import { clear, h } from "../dom.js";

export function registerView({ container }) {
  const error = h("div", { class: "form-error", role: "alert" });
  const email = h("input", { id: "email", type: "email", autocomplete: "username", required: true });
  const password = h("input", { id: "password", type: "password", autocomplete: "new-password", required: true, minlength: "12" });
  const submit = h("button", { class: "button primary", type: "submit" }, "Solicitar acceso");
  const card = h("form", { class: "auth-card" });

  async function onSubmit(event) {
    event.preventDefault();
    error.textContent = "";
    submit.disabled = true;
    try {
      await api.register(email.value.trim(), password.value);
      clear(card).append(
        brand(),
        h("h1", {}, "Solicitud enviada"),
        h("p", { class: "form-ok", role: "status" }, "Un administrador debe aprobar tu cuenta antes de que puedas entrar."),
        h("a", { href: "#/login" }, "Volver al acceso"),
      );
    } catch (failure) {
      error.textContent = failure.status === 403 ? "El registro está cerrado. Pide a un administrador que cree tu cuenta." : failure.message;
      submit.disabled = false;
    }
  }

  card.addEventListener("submit", onSubmit);
  card.append(
    brand(),
    h("h1", {}, "Solicitar acceso"),
    h("div", { class: "field" }, h("label", { for: "email" }, "Correo electrónico"), email),
    h("div", { class: "field" }, h("label", { for: "password" }, "Contraseña (mínimo 12 caracteres)"), password),
    error,
    submit,
    h("p", { class: "auth-alt" }, h("a", { href: "#/login" }, "Ya tengo cuenta")),
  );
  container.append(h("main", { class: "auth" }, card));
  email.focus();
}
