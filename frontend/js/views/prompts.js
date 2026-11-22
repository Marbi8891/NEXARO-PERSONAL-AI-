// Biblioteca de prompts por organización (ADR-0023): lista, alta/edición, historial, catálogo y
// «Usar en el chat» (rellena las variables, el servidor renderiza y el chat recibe el borrador
// para que el usuario lo revise y lo envíe). Todo el texto se pinta con h(): nunca innerHTML.
import { api } from "../api.js";
import { confirmDialog } from "../components/dialog.js";
import { field } from "../components/form.js";
import { emptyState, errorState, loadingState } from "../components/states.js";
import { dataTable } from "../components/table.js";
import { toast } from "../components/toast.js";
import { append, clear, formatDate, h } from "../dom.js";
import { navigate } from "../router.js";
import { setChatDraft } from "../state.js";

const canWrite = (org) => ["owner", "admin", "member"].includes(org.role);
const VARIABLE = /{{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}}/g;

// Variables de la plantilla que aún no están declaradas: se añaden como texto opcional.
export function variablesFor(template, declared = []) {
  const used = [...new Set([...template.matchAll(VARIABLE)].map((m) => m[1]))];
  return used.map((name) => declared.find((v) => v.name === name) ?? { name, label: name, type: "text", required: false });
}

function textarea(id, label, value = "", attributes = {}) {
  const input = h("textarea", { id, rows: "4", ...attributes });
  input.value = value;
  return { input, element: h("div", { class: "field" }, h("label", { for: id }, label), input) };
}

function modal(title, body, actions) {
  return new Promise((resolve) => {
    let answer = null;
    const dialog = h("dialog", { class: "dialog", "aria-labelledby": "prompt-dialog-title" }, h("h2", { id: "prompt-dialog-title" }, title), body, h("div", { class: "dialog-actions" }, actions.map(({ label, value, primary }) => h("button", { class: primary ? "button" : "button secondary", type: "button", onclick: () => close(typeof value === "function" ? value() : value) }, label))));
    function close(result) {
      if (result === undefined) return; // validación fallida: el diálogo sigue abierto
      answer = result;
      if (typeof dialog.close === "function") dialog.close();
      else finish();
    }
    function finish() {
      dialog.remove();
      resolve(answer);
    }
    dialog.addEventListener("close", finish);
    document.body.append(dialog);
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
  });
}

export async function promptsView({ container, shell }) {
  shell.setTitle("Prompts");
  const body = h("div", { class: "page-body stack" });
  container.append(body);

  let organizations;
  try {
    organizations = (await api.organizations()).organizations;
  } catch (error) {
    body.append(errorState(error.message));
    return;
  }
  if (organizations.length === 0) {
    body.append(emptyState({ title: "Sin organizaciones", text: "La biblioteca de prompts pertenece a una organización. Crea una o pide que te añadan.", action: h("a", { class: "button secondary", href: "#/organizations" }, "Ver organizaciones") }));
    return;
  }

  const picker = field({ id: "prompts-org", label: "Organización", options: organizations.map((o) => [o.id, o.name]), value: organizations[0].id });
  const content = h("div", { class: "stack" });
  const current = () => organizations.find((o) => o.id === picker.input.value);
  picker.input.addEventListener("change", () => show(current()));
  append(body, [organizations.length > 1 ? h("section", { class: "card" }, h("div", { class: "inline-form" }, picker.element)) : null, content]);
  await show(organizations[0]);

  async function show(org) {
    clear(content).append(loadingState());
    try {
      const [list, catalogue] = await Promise.all([api.prompts(org.id), api.promptCatalogue()]);
      const installed = new Set(list.items.map((p) => p.catalogue_id).filter(Boolean));
      append(clear(content), [promptTable(org, list), canWrite(org) ? editor(org, null) : null, catalogueTable(org, catalogue, installed)]);
    } catch (error) {
      clear(content).append(errorState(error.message, { onRetry: () => show(org) }));
    }
  }

  function promptTable(org, list) {
    const writable = canWrite(org);
    const table = dataTable({
      caption: `Prompts de ${org.name} (${list.total})`,
      rows: list.items,
      empty: { title: "Biblioteca vacía", text: writable ? "Crea un prompt o instala uno del catálogo." : "Aún no hay prompts en esta organización." },
      columns: [
        { key: "name", label: "Nombre" },
        { key: "category", label: "Categoría" },
        { key: "tags", label: "Etiquetas", value: (p) => p.tags.join(", ") || "—" },
        { key: "version", label: "Versión", search: false, render: (p) => `v${p.version}` },
        {
          key: "actions", label: "Acciones", sortable: false, search: false, className: "actions",
          render: (p) => h("span", { class: "row-actions" },
            h("button", { class: "button small", type: "button", "aria-label": `Usar ${p.name} en el chat`, onclick: () => usePrompt(org, p) }, "Usar en el chat"),
            h("button", { class: "button secondary small", type: "button", "aria-label": `Historial de ${p.name}`, onclick: () => history(org, p) }, "Historial"),
            writable ? h("button", { class: "button secondary small", type: "button", "aria-label": `Editar ${p.name}`, onclick: () => { const section = editor(org, p); content.querySelector("#prompt-editor")?.replaceWith(section); section.scrollIntoView?.({ block: "start" }); } }, "Editar") : null,
            writable ? h("button", { class: "button danger small", type: "button", "aria-label": `Borrar ${p.name}`, onclick: () => remove(org, p) }, "Borrar") : null),
        },
      ],
    });
    return table.element;
  }

  function editor(org, prompt) {
    const name = field({ id: "pr-name", label: "Nombre", required: true, minlength: "2", maxlength: "120", value: prompt?.name ?? "" });
    const category = field({ id: "pr-category", label: "Categoría", required: true, maxlength: "80", value: prompt?.category ?? "" });
    const tags = field({ id: "pr-tags", label: "Etiquetas", hint: "Separadas por comas", value: prompt?.tags.join(", ") ?? "" });
    const description = field({ id: "pr-description", label: "Descripción", maxlength: "1000", value: prompt?.description ?? "" });
    const system = textarea("pr-system", "Instrucciones (opcional)", prompt?.system_prompt ?? "", { maxlength: "20000" });
    const template = textarea("pr-template", "Plantilla", prompt?.user_template ?? "", { required: true, maxlength: "20000", "aria-describedby": "pr-template-hint" });
    const changelog = field({ id: "pr-changelog", label: "Qué cambia", maxlength: "200", value: "" });
    const form = h(
      "form",
      {
        class: "stack",
        onsubmit: async (event) => {
          event.preventDefault();
          const payload = {
            name: name.input.value.trim(),
            category: category.input.value.trim(),
            tags: tags.input.value.split(",").map((t) => t.trim()).filter(Boolean),
            description: description.input.value.trim(),
            system_prompt: system.input.value,
            user_template: template.input.value,
            variables: variablesFor(template.input.value, prompt?.variables ?? []),
          };
          try {
            if (prompt) await api.updatePrompt(org.id, prompt.id, { ...payload, changelog: changelog.input.value.trim() || "Cambios" });
            else await api.createPrompt(org.id, payload);
            toast(prompt ? "Prompt actualizado (nueva versión)." : "Prompt creado.");
            await show(org);
          } catch (error) {
            toast(error.message, { error: true });
          }
        },
      },
      h("div", { class: "inline-form" }, name.element, category.element, tags.element),
      description.element, system.element, template.element,
      h("span", { class: "hint", id: "pr-template-hint" }, "Usa {{variable}} para los huecos que rellenarás al usarlo."),
      prompt ? changelog.element : null,
      h("div", { class: "row-actions" }, h("button", { class: "button", type: "submit" }, prompt ? "Guardar versión nueva" : "Crear prompt"), prompt ? h("button", { class: "button secondary", type: "button", onclick: () => show(org) }, "Cancelar") : null),
    );
    return h("section", { class: "card", id: "prompt-editor" }, h("h2", {}, prompt ? `Editar «${prompt.name}»` : "Nuevo prompt"), form);
  }

  async function usePrompt(org, prompt) {
    const inputs = prompt.variables.map((v, i) => {
      const id = `pv-${i}`;
      const label = `${v.label || v.name}${v.required ? " *" : ""}`;
      return { name: v.name, ...(v.type === "textarea" ? textarea(id, label, v.default ?? "") : field({ id, label, value: v.default ?? "" })) };
    });
    const values = await modal(`Usar «${prompt.name}»`, h("div", { class: "stack" }, inputs.length ? inputs.map((i) => i.element) : h("p", {}, "Este prompt no tiene variables.")), [
      { label: "Cancelar", value: null },
      { label: "Preparar mensaje", primary: true, value: () => Object.fromEntries(inputs.map((i) => [i.name, i.input.value])) },
    ]);
    if (!values) return;
    try {
      const rendered = await api.renderPrompt(org.id, prompt.id, values);
      setChatDraft(rendered.message);
      toast("Mensaje preparado: revísalo y envíalo en el chat.");
      navigate("/chat");
    } catch (error) {
      toast(error.message, { error: true });
    }
  }

  async function history(org, prompt) {
    let versions;
    try {
      versions = (await api.promptVersions(org.id, prompt.id)).items;
    } catch (error) {
      return toast(error.message, { error: true });
    }
    const list = h("ol", { class: "stack", reversed: true }, versions.map((v) => h("li", {}, h("strong", {}, `v${v.version}`), ` · ${formatDate(v.created_at)} · ${v.changelog || "—"}`,
      canWrite(org) && v.version !== prompt.version ? h("button", { class: "button secondary small", type: "button", onclick: async () => {
        try {
          await api.restorePrompt(org.id, prompt.id, v.version);
          toast(`Restaurada la versión ${v.version} como versión nueva.`);
          document.querySelector("dialog")?.close();
          await show(org);
        } catch (error) {
          toast(error.message, { error: true });
        }
      } }, "Restaurar") : null)));
    await modal(`Historial de «${prompt.name}»`, list, [{ label: "Cerrar", value: null }]);
  }

  async function remove(org, prompt) {
    if (!(await confirmDialog({ title: "¿Borrar prompt?", message: `«${prompt.name}» y todo su historial se borrarán de ${org.name}.`, confirmLabel: "Borrar", danger: true }))) return;
    try {
      await api.deletePrompt(org.id, prompt.id);
      toast("Prompt borrado.");
      await show(org);
    } catch (error) {
      toast(error.message, { error: true });
    }
  }

  function catalogueTable(org, catalogue, installed) {
    return dataTable({
      caption: `Catálogo (${catalogue.total})`,
      rows: catalogue.items,
      filters: [{ key: "category", label: "Categoría", options: catalogue.categories.map((c) => [c, c]) }],
      columns: [
        { key: "name", label: "Nombre" },
        { key: "category", label: "Categoría" },
        { key: "description", label: "Descripción" },
        {
          key: "actions", label: "Acciones", sortable: false, search: false, className: "actions",
          render: (p) => installed.has(p.id)
            ? h("span", { class: "hint" }, "Instalado")
            : canWrite(org)
              ? h("button", { class: "button secondary small", type: "button", "aria-label": `Instalar ${p.name}`, onclick: async () => {
                  try {
                    await api.installPrompt(org.id, p.id);
                    toast(`«${p.name}» añadido a ${org.name}.`);
                    await show(org);
                  } catch (error) {
                    toast(error.message, { error: true });
                  }
                } }, "Instalar")
              : null,
        },
      ],
    }).element;
  }
}
