import { api } from "../api.js";
import { brand } from "../components/brand.js";
import { field } from "../components/form.js";
import { h } from "../dom.js";
import { navigate } from "../router.js";
import { getNotice, rememberConversation, setNotice, setUser } from "../state.js";

export function loginView({ container }) {
  document.title = "Iniciar sesión · NEXARO";
  const error = h("div", { class: "form-error", role: "alert" });
  const notice = getNotice();
  const email = field({ id: "email", label: "Correo electrónico", type: "email", autocomplete: "username", required: true });
  const password = field({ id: "password", label: "Contraseña", type: "password", autocomplete: "current-password", required: true });
  const submit = h("button", { class: "button", type: "submit" }, "Entrar");

  async function onSubmit(event) {
    event.preventDefault();
    error.textContent = "";
    setNotice("");
    submit.disabled = true;
    try {
      const data = await api.login(email.input.value.trim(), password.input.value);
      rememberConversation(null);
      setUser(data.user);
      navigate("/chat");
    } catch (failure) {
      error.textContent = failure.message;
      password.input.value = "";
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
        email.element,
        password.element,
        error,
        submit,
        h("p", { class: "auth-alt" }, "¿Sin cuenta? ", h("a", { href: "#/register" }, "Solicitar acceso")),
      ),
    ),
  );
  email.input.focus();
}
