import { api } from "../api.js";
import { confirmDialog } from "../components/dialog.js";
import { toast } from "../components/toast.js";
import { clear, h } from "../dom.js";

const CATEGORIES = [
  ["general", "General"], ["development", "Desarrollo"], ["cybersecurity", "Ciberseguridad"],
  ["ai_data", "IA y datos"], ["education", "Educación"], ["business", "Negocio"],
  ["research", "Investigación"], ["productivity", "Productividad"], ["custom", "Personalizado"],
];

export async function agentsView({ container, shell }) {
  shell.setTitle("Agentes");
  let orgs = [];
  let selectedOrg = "";
  let editing = null;
  const orgSelect = h("select", { "aria-label": "Organización" });
  const list = h("div", { class: "stack" });
  const formWrap = h("section", { class: "card", hidden: true });
  const title = h("h2", {}, "Crear agente");
  const name = h("input", { maxlength: "80", required: true, placeholder: "Nombre del agente" });
  const description = h("input", { maxlength: "500", required: true, placeholder: "Qué hace este agente" });
  const category = h("select", {}, CATEGORIES.map(([value, label]) => h("option", { value }, label)));
  const model = h("input", { maxlength: "120", placeholder: "Modelo (opcional, usa el predeterminado)" });
  const prompt = h("textarea", { rows: "8", maxlength: "12000", required: true, placeholder: "Instrucciones del agente..." });
  const status = h("select", {}, h("option", { value: "active" }, "Activo"), h("option", { value: "disabled" }, "Desactivado"));
  const save = h("button", { class: "button", type: "button" }, "Guardar agente");
  const cancel = h("button", { class: "button secondary", type: "button" }, "Cancelar");
  formWrap.append(title,
    h("div", { class: "field" }, h("label", {}, "Nombre"), name),
    h("div", { class: "field" }, h("label", {}, "Descripción"), description),
    h("div", { class: "field" }, h("label", {}, "Categoría"), category),
    h("div", { class: "field" }, h("label", {}, "Modelo"), model),
    h("div", { class: "field" }, h("label", {}, "Instrucciones"), prompt),
    h("div", { class: "field" }, h("label", {}, "Estado"), status),
    h("div", { class: "row-actions" }, save, cancel),
    h("p", { class: "hint" }, "Esta primera versión solo admite agentes de instrucciones. No pueden ejecutar herramientas, terminal, red ni modificar archivos.")
  );
  function resetForm() {
    editing = null;
    title.textContent = "Crear agente";
    name.value = description.value = model.value = prompt.value = "";
    category.value = "custom";
    status.value = "active";
    formWrap.hidden = true;
  }
  function openForm(agent = null) {
    editing = agent;
    title.textContent = agent ? "Editar agente" : "Crear agente";
    name.value = agent?.name || "";
    description.value = agent?.description || "";
    category.value = agent?.category || "custom";
    model.value = agent?.model || "";
    prompt.value = agent?.system_prompt || "";
    status.value = agent?.status || "active";
    formWrap.hidden = false;
    name.focus();
  }
  cancel.addEventListener("click", resetForm);
  save.addEventListener("click", async () => {
    const payload = {
      name: name.value.trim(), description: description.value.trim(),
      category: category.value, model: model.value.trim() || null,
      system_prompt: prompt.value.trim(), tools: [],
      permissions: { filesystem: "none", terminal: false, network: false },
      memory: { enabled: false, scope: "none" }, autonomy: "assisted",
      ...(editing ? { status: status.value } : {}),
    };
    if (!payload.name || !payload.description || !payload.system_prompt) {
      toast("Completa el nombre, la descripción y las instrucciones.", { error: true }); return;
    }
    save.disabled = true;
    try {
      if (editing) await api.updateOrganizationAgent(selectedOrg, editing.id, payload);
      else await api.createOrganizationAgent(selectedOrg, payload);
      toast(editing ? "Agente actualizado." : "Agente creado.");
      resetForm(); await refresh();
    } catch (error) { toast(error.message, { error: true }); }
    finally { save.disabled = false; }
  });
  async function refresh() {
    if (!selectedOrg) { clear(list).append(h("p", { class: "empty" }, "Selecciona una organización.")); return; }
    try {
      const { agents } = await api.organizationAgents(selectedOrg);
      clear(list);
      if (!agents.length) list.append(h("p", { class: "empty" }, "Todavía no hay agentes personalizados."));
      for (const agent of agents) {
        const card = h("article", { class: "card" },
          h("div", { class: "switch-row" }, h("div", {}, h("h2", {}, agent.name), h("p", {}, agent.description)), h("span", { class: `badge ${agent.status === "active" ? "ok" : "warn"}` }, agent.status === "active" ? "Activo" : "Desactivado")),
          h("p", { class: "hint" }, `${agent.category} · ${agent.model || "Modelo predeterminado"}`),
          h("div", { class: "row-actions" },
            h("button", { class: "button secondary small", type: "button", onclick: () => openForm(agent) }, "Editar"),
            h("button", { class: "button danger small", type: "button", onclick: async () => {
              const ok = await confirmDialog({ title: "Eliminar agente", message: `Eliminar «${agent.name}»? Esta acción no se puede deshacer.`, confirmLabel: "Eliminar", danger: true });
              if (!ok) return;
              try { await api.deleteOrganizationAgent(selectedOrg, agent.id); toast("Agente eliminado."); await refresh(); }
              catch (error) { toast(error.message, { error: true }); }
            } }, "Eliminar")
          )
        );
        list.append(card);
      }
    } catch (error) { clear(list).append(h("p", { class: "empty" }, error.message)); }
  }
  orgSelect.addEventListener("change", () => { selectedOrg = orgSelect.value; resetForm(); refresh(); });
  const create = h("button", { class: "button", type: "button", onclick: () => openForm() }, "+ Crear agente");
  container.append(h("div", { class: "stack" },
    h("section", { class: "card" }, h("h2", {}, "Agentes personalizados"), h("p", { class: "hint" }, "Crea perfiles especializados con instrucciones propias. Las capacidades ejecutables se habilitarán cuando exista el runtime seguro."), h("div", { class: "toolbar" }, h("div", { class: "toolbar-item grow" }, h("label", {}, "Organización"), orgSelect), create)),
    formWrap, list
  ));
  try {
    const result = await api.organizations();
    orgs = result.organizations || [];
    orgSelect.replaceChildren(...orgs.map(o => h("option", { value: o.id }, o.name)));
    if (!orgs.length) { orgSelect.disabled = true; create.disabled = true; list.append(h("p", { class: "empty" }, "Necesitas pertenecer a una organización para administrar agentes.")); return; }
    selectedOrg = orgs[0].id;
    orgSelect.value = selectedOrg;
    await refresh();
  } catch (error) { toast(error.message, { error: true }); }
}
