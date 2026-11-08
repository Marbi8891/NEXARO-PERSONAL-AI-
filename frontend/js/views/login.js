import { api } from "../api.js";
import { brand } from "../components/brand.js";
import { h } from "../dom.js";
import { navigate } from "../router.js";
import { getNotice, rememberConversation, setNotice, setUser } from "../state.js";

export function loginView({ container }) {
  const error = h("div", { class: "form-error", role: "alert" });
  const notice = getNotice();
  const email = h("input", { id: "email", type: "email", autocomplete: "username", required: true });
  const password = h("input", { id: "password", type: "password", autocomplete: "current-password", required: true });
  const submit = h("button", { class: "button primary", type: "submit" }, "Entrar");

  async function onSubmit(event) {
    event.preventDefault();
    error.textContent = "";
    setNotice("");
    submit.disabled = true;
    try {
      const data = await api.login(email.value.trim(), password.value);
      rememberConversation(null);
      setUser(data.user);
      navigate("/chat");
    } catch (failure) {
      error.textContent = failure.message;
      password.value = "";
      submit.disabled = false;
    }
  }

  container.append(
    h(
      "main",
      { class: "auth" },
      h(
        "form",
        { class: "auth-card", onsubmit: onSubmit },
        brand(),
        h("h1", {}, "Iniciar sesión"),
        notice ? h("div", { class: "form-ok", role: "status" }, notice) : null,
        h("div", { class: "field" }, h("label", { for: "email" }, "Correo electrónico"), email),
        h("div", { class: "field" }, h("label", { for: "password" }, "Contraseña"), password),
        error,
        submit,
        h("p", { class: "auth-alt" }, "¿Sin cuenta? ", h("a", { href: "#/register" }, "Solicitar acceso")),
      ),
    ),
  );
  email.focus();
}
