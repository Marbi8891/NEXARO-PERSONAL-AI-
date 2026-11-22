// Agentes personales: crear, editar, duplicar, activar/desactivar y borrar. Solo los del usuario
// (lo impone el servidor). Un agente parte de uno predefinido y solo puede quitarle herramientas.
import { api } from "../api.js";
import { confirmDialog } from "../components/dialog.js";
import { field } from "../components/form.js";
import { errorState, loadingState } from "../components/states.js";
import { dataTable } from "../components/table.js";
import { toast } from "../components/toast.js";
import { append, clear, formatDate, h } from "../dom.js";

const TOOL_LABELS = { documents: "Consultar documentos" };

export async function agentsView({ container, shell }) {
  shell.setTitle("Agentes");
  const body = h("div", { class: "page-body stack" });
  container.append(body);

  let builtins = [];
  let models = [];
  try {
    const [agentList, modelInfo] = await Promise.all([api.agents(), api.models().catch(() => null)]);
    builtins = agentList.agents.filter((a) => !a.custom);
    models = modelInfo?.selectable ? modelInfo.models.map((m) => m.name) : [];
  } catch (error) {
    body.append(errorState(error.message));
    return;
  }

  const formCard = h("section", { class: "card" });
  const listArea = h("div", { class: "stack" });
  append(body, [formCard, listArea]);
  showForm(null);
  await reload();

  async function reload() {
    clear(listArea).append(loadingState());
    try {
      const { agents } = await api.customAgents();
      const table = dataTable({
        caption: "Tus agentes",
        rows: agents,
        empty: { title: "Aún no tienes agentes", text: "Crea el primero con el formulario de arriba." },
        columns: [
          { key: "name", label: "Nombre" },
          { key: "category", label: "Categoría" },
          { key: "base_agent", label: "Basado en", value: (a) => builtins.find((b) => b.id === a.base_agent)?.name ?? a.base_agent },
          { key: "status", label: "Estado", value: (a) => (a.status === "active" ? "Activo" : "Desactivado") },
          { key: "updated_at", label: "Actualizado", value: (a) => formatDate(a.updated_at) },
          {
            key: "actions",
            label: "Acciones",
            sortable: false,
            search: false,
            className: "actions",
            render: (a) =>
              h(
                "div",
                { class: "row-actions" },
                h("button", { class: "button secondary small", type: "button", "aria-label": `Editar ${a.name}`, onclick: () => showForm(a) }, "Editar"),
                h("button", { class: "button secondary small", type: "button", "aria-label": `Duplicar ${a.name}`, onclick: () => run(() => api.duplicateCustomAgent(a.id), "Copia creada (desactivada).") }, "Duplicar"),
                h("button", { class: "button secondary small", type: "button", "aria-label": `${a.status === "active" ? "Desactivar" : "Activar"} ${a.name}`, onclick: () => run(() => api.updateCustomAgent(a.id, { status: a.status === "active" ? "disabled" : "active" }), a.status === "active" ? "Agente desactivado." : "Agente activado.") }, a.status === "active" ? "Desactivar" : "Activar"),
                h("button", { class: "button danger small", type: "button", "aria-label": `Borrar ${a.name}`, onclick: async () => {
                  if (!(await confirmDialog({ title: "¿Borrar agente?", message: `«${a.name}» dejará de estar disponible en el chat. Las conversaciones se conservan.`, confirmLabel: "Borrar", danger: true }))) return;
                  await run(() => api.deleteCustomAgent(a.id), "Agente borrado.");
                } }, "Borrar"),
              ),
          },
        ],
      });
      append(clear(listArea), [table.element]);
    } catch (error) {
      clear(listArea).append(errorState(error.message, { onRetry: reload }));
    }
  }

  async function run(action, message) {
    try {
      await action();
      toast(message);
      showForm(null);
      await reload();
    } catch (error) {
      toast(error.message, { error: true });
    }
  }

  function showForm(agent) {
    const editing = Boolean(agent);
    const name = field({ id: "agent-name", label: "Nombre", required: true, maxlength: "80", value: agent?.name ?? "" });
    const description = field({ id: "agent-description", label: "Descripción", maxlength: "300", value: agent?.description ?? "" });
    const category = field({ id: "agent-category", label: "Categoría", maxlength: "40", value: agent?.category ?? "general" });
    const base = field({ id: "agent-base", label: "Basado en", options: builtins.map((b) => [b.id, b.name]), value: agent?.base_agent ?? "general", hint: "Hereda sus reglas de seguridad y, como máximo, sus herramientas." });
    const instructions = h("textarea", { id: "agent-instructions", rows: "5", maxlength: "4000", "aria-describedby": "agent-instructions-hint" });
    instructions.value = agent?.instructions ?? "";
    const modelOptions = [["auto", "Automático"], ...models.map((m) => [m, m])];
    if (agent?.model && !models.includes(agent.model)) modelOptions.push([agent.model, `${agent.model} (no instalado)`]);
    const model = field({ id: "agent-model", label: "Modelo", options: modelOptions, value: agent?.model ?? "auto" });
    const toolsBox = h("fieldset", { class: "choices" }, h("legend", {}, "Herramientas"));
    function drawTools() {
      const allowed = builtins.find((b) => b.id === base.input.value)?.tools ?? [];
      const selected = agent && agent.base_agent === base.input.value ? agent.tools : allowed;
      toolsBox.replaceChildren(
        h("legend", {}, "Herramientas"),
        ...(allowed.length
          ? allowed.map((tool) => h("label", { class: "choice" }, h("input", { type: "checkbox", name: "agent-tool", value: tool, checked: selected.includes(tool) }), h("span", {}, TOOL_LABELS[tool] ?? tool)))
          : [h("span", { class: "hint" }, "Este agente base no tiene herramientas.")]),
      );
    }
    base.input.addEventListener("change", drawTools);
    drawTools();

    const form = h(
      "form",
      {
        id: "agent-form",
        class: "stack",
        onsubmit: async (event) => {
          event.preventDefault();
          const payload = {
            name: name.input.value.trim(),
            description: description.input.value.trim(),
            category: category.input.value.trim() || "general",
            base_agent: base.input.value,
            instructions: instructions.value,
            tools: [...toolsBox.querySelectorAll("input[name=agent-tool]:checked")].map((i) => i.value),
            model: model.input.value,
          };
          if (!payload.name) return toast("Ponle un nombre al agente.", { error: true });
          await run(() => (editing ? api.updateCustomAgent(agent.id, payload) : api.createCustomAgent(payload)), editing ? "Agente guardado." : "Agente creado. Ya puedes elegirlo en el chat.");
        },
      },
      name.element,
      description.element,
      category.element,
      base.element,
      h("div", { class: "field" }, h("label", { for: "agent-instructions" }, "Instrucciones"), instructions, h("span", { class: "hint", id: "agent-instructions-hint" }, "Cómo debe trabajar este agente. No pueden saltarse las reglas de seguridad de NEXARO.")),
      toolsBox,
      model.element,
      h("div", { class: "dialog-actions" }, editing ? h("button", { class: "button secondary", type: "button", onclick: () => showForm(null) }, "Cancelar edición") : null, h("button", { class: "button", type: "submit" }, editing ? "Guardar cambios" : "Crear agente")),
    );
    clear(formCard).append(h("h2", {}, editing ? `Editar «${agent.name}»` : "Nuevo agente"), form);
  }
}
