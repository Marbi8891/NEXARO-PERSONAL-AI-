// Módulo Developer: claves de API de una organización, su uso real y cómo llamar a /api/v1.
// Solo propietarios y administradores de la organización gestionan claves (lo impone el servidor).
import { api } from "../api.js";
import { confirmDialog } from "../components/dialog.js";
import { field } from "../components/form.js";
import { emptyState, errorState, loadingState } from "../components/states.js";
import { dataTable } from "../components/table.js";
import { toast } from "../components/toast.js";
import { append, clear, formatDate, h } from "../dom.js";

const STATUS = { active: ["ok", "Activa"], expired: ["warn", "Caducada"], revoked: ["bad", "Revocada"] };
const EXPIRY = [["", "Nunca"], ["30", "30 días"], ["90", "90 días"], ["365", "1 año"]];
const canManage = (org) => org.role === "owner" || org.role === "admin";

export async function developerView({ container, shell }) {
  shell.setTitle("Developer");
  const body = h("div", { class: "page-body stack" });
  container.append(body);

  let organizations;
  try {
    organizations = (await api.organizations()).organizations.filter(canManage);
  } catch (error) {
    body.append(errorState(error.message));
    return;
  }
  if (organizations.length === 0) {
    body.append(
      emptyState({
        title: "Sin acceso a claves de API",
        text: "Las claves las gestionan los propietarios y administradores de una organización. Pide a uno de ellos que te añada con ese rol.",
        action: h("a", { class: "button secondary", href: "#/organizations" }, "Ver organizaciones"),
      }),
    );
    return;
  }

  const content = h("div", { class: "stack" });
  const picker = field({ id: "dev-org", label: "Organización", options: organizations.map((o) => [o.id, o.name]), value: organizations[0].id });
  picker.input.addEventListener("change", () => show(current()));
  const current = () => organizations.find((o) => o.id === picker.input.value);
  append(body, [organizations.length > 1 ? h("section", { class: "card" }, picker.element) : null, content]);
  await show(organizations[0]);

  async function show(org) {
    clear(content).append(loadingState());
    try {
      const [{ api_keys: keys }, usage] = await Promise.all([api.apiKeys(org.id), api.organizationUsage(org.id)]);
      const reload = () => show(org);

      const name = field({ id: "key-name", label: "Nombre de la clave", required: true, maxlength: "80", hint: "Para reconocerla: «CI», «Producción»..." });
      const expiry = field({ id: "key-expiry", label: "Caduca", options: EXPIRY, value: "" });
      const form = h(
        "form",
        {
          class: "inline-form",
          onsubmit: async (event) => {
            event.preventDefault();
            try {
              const days = expiry.input.value ? Number(expiry.input.value) : null;
              const created = await api.createApiKey(org.id, name.input.value.trim(), days);
              await reload();
              clear(content.querySelector("[data-secret]")).append(revealSecret(created));
              content.querySelector("[data-secret] input")?.focus();
            } catch (error) {
              toast(error.message, { error: true });
            }
          },
        },
        name.element,
        expiry.element,
        h("button", { class: "button", type: "submit" }, "Crear clave"),
      );

      const keysTable = dataTable({
        caption: `Claves de ${org.name}`,
        rows: keys,
        empty: { title: "Aún no hay claves", text: "Crea la primera con el formulario de arriba." },
        initialSort: null,
        columns: [
          { key: "name", label: "Nombre" },
          { key: "prefix", label: "Clave", className: "mono", render: (k) => h("code", {}, `${k.prefix}…`) },
          { key: "status", label: "Estado", value: (k) => STATUS[k.status][1], render: (k) => h("span", { class: `badge ${STATUS[k.status][0]}` }, STATUS[k.status][1]) },
          { key: "created_at", label: "Creada", value: (k) => formatDate(k.created_at) },
          { key: "last_used_at", label: "Último uso", value: (k) => (k.last_used_at ? formatDate(k.last_used_at) : "Nunca") },
          { key: "expires_at", label: "Caduca", value: (k) => (k.expires_at ? formatDate(k.expires_at) : "No caduca") },
          {
            key: "actions",
            label: "Acciones",
            sortable: false,
            search: false,
            className: "actions",
            render: (k) =>
              k.status === "revoked"
                ? null
                : h("button", { class: "button danger small", type: "button", "aria-label": `Revocar ${k.name}`, onclick: async () => {
                    if (!(await confirmDialog({ title: "¿Revocar clave?", message: `«${k.name}» dejará de funcionar de inmediato. No se puede deshacer.`, confirmLabel: "Revocar", danger: true }))) return;
                    try {
                      await api.revokeApiKey(org.id, k.id);
                      toast("Clave revocada.");
                      await reload();
                    } catch (error) {
                      toast(error.message, { error: true });
                    }
                  } }, "Revocar"),
          },
        ],
      });

      const usageTable = dataTable({
        caption: `Uso por clave (${usage.days} días)`,
        rows: usage.keys,
        empty: { title: "Sin uso registrado", text: "Aparecerá aquí cuando alguna clave haga peticiones a /api/v1/chat." },
        columns: [
          { key: "name", label: "Clave", value: (u) => u.name ?? "(clave eliminada)" },
          { key: "requests", label: "Peticiones" },
          { key: "errors", label: "Errores" },
          { key: "input_tokens", label: "Tokens entrada" },
          { key: "output_tokens", label: "Tokens salida" },
          { key: "cost_usd", label: "Coste (USD)", value: (u) => u.cost_usd.toFixed(4) },
        ],
      });

      const example = `curl -X POST ${location.origin}/api/v1/chat \\\n  -H "Authorization: Bearer TU_CLAVE" \\\n  -H "Content-Type: application/json" \\\n  -d '{"message": "Hola"}'`;
      append(clear(content), [
        h("section", { class: "card" }, h("h2", {}, "Nueva clave de API"), h("p", { class: "hint" }, "La clave actúa en tu nombre dentro de esta organización y deja de valer si pierdes tu acceso a ella."), form),
        h("div", { "data-secret": "" }),
        keysTable.element,
        usageTable.element,
        h("section", { class: "card" }, h("h2", {}, "Cómo usarla"), h("p", { class: "hint" }, "Envía la clave en la cabecera Authorization. La respuesta incluye conversation_id para continuar la conversación."), h("pre", { class: "code-block" }, h("code", {}, example))),
      ]);
    } catch (error) {
      clear(content).append(errorState(error.message, { onRetry: () => show(org) }));
    }
  }

  function revealSecret(created) {
    const input = h("input", { type: "text", readOnly: true, value: created.secret, "aria-label": "Clave de API (cópiala ahora)", class: "mono", onfocus: (event) => event.target.select() });
    const copy = h("button", { class: "button secondary", type: "button", onclick: async () => {
      try {
        await navigator.clipboard.writeText(created.secret);
        toast("Clave copiada.");
      } catch {
        input.select();
        toast("Cópiala manualmente: tu navegador no permite el portapapeles.", { error: true });
      }
    } }, "Copiar");
    return h(
      "section",
      { class: "card secret-card", role: "alert" },
      h("h2", {}, `Clave «${created.name}» creada`),
      h("p", {}, "Cópiala ahora: es la única vez que se muestra completa. Si la pierdes, revócala y crea otra."),
      h("div", { class: "secret-row" }, input, copy),
    );
  }
}
