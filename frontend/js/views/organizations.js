import { api } from "../api.js";
import { confirmDialog } from "../components/dialog.js";
import { field } from "../components/form.js";
import { errorState, loadingState } from "../components/states.js";
import { dataTable } from "../components/table.js";
import { toast } from "../components/toast.js";
import { append, clear, h } from "../dom.js";
import { getUser } from "../state.js";

const ROLES = [["owner", "Propietario"], ["admin", "Administrador"], ["member", "Miembro"], ["viewer", "Lector"]];
const roleLabel = (role) => ROLES.find(([key]) => key === role)?.[1] ?? role;

export async function organizationsView({ container, shell }) {
  shell.setTitle("Organizaciones");
  const isPlatformAdmin = getUser().role === "admin";
  const listArea = h("div", {});
  const detail = h("div", { class: "stack" });

  async function guarded(action, success) {
    try {
      await action();
      toast(success);
    } catch (error) {
      toast(error.message, { error: true });
    }
  }

  async function loadOrganizations() {
    clear(listArea).append(loadingState());
    try {
      const { organizations } = await api.organizations();
      const table = dataTable({
        caption: "Tus organizaciones",
        rows: organizations,
        empty: { title: "No perteneces a ninguna organización", text: isPlatformAdmin ? "Crea la primera con el formulario de arriba." : "Un administrador debe añadirte a una." },
        columns: [
          { key: "name", label: "Nombre", render: (org) => h("button", { class: "link-button", type: "button", onclick: () => showMembers(org) }, org.name) },
          { key: "slug", label: "Identificador", className: "mono" },
          { key: "role", label: "Tu rol", value: (org) => roleLabel(org.role) },
        ],
      });
      clear(listArea).append(table.element);
    } catch (error) {
      clear(listArea).append(errorState(error.message, { onRetry: loadOrganizations }));
    }
  }

  async function showMembers(org) {
    clear(detail).append(loadingState());
    try {
      const reload = () => showMembers(org);
      const { members } = await api.members(org.id);
      const canManage = org.role === "owner" || org.role === "admin";

      const email = field({ id: "member-email", label: "Correo de un usuario existente", type: "email", required: true });
      const role = field({ id: "member-role", label: "Rol", options: ROLES, value: "member" });
      const addForm = h(
        "form",
        { class: "inline-form", onsubmit: (event) => { event.preventDefault(); guarded(async () => { await api.addMember(org.id, email.input.value.trim(), role.input.value); await reload(); }, "Miembro añadido."); } },
        email.element,
        role.element,
        h("button", { class: "button", type: "submit" }, "Añadir"),
      );

      const table = dataTable({
        caption: `Miembros de ${org.name}`,
        rows: members,
        empty: { title: "Sin miembros" },
        columns: [
          { key: "email", label: "Correo" },
          {
            key: "role",
            label: "Rol",
            value: (m) => roleLabel(m.role),
            render: (m) => {
              const select = h("select", { "aria-label": `Rol de ${m.email}`, disabled: !canManage }, ROLES.map(([value, text]) => h("option", { value, selected: value === m.role }, text)));
              select.addEventListener("change", () => guarded(async () => { await api.setMemberRole(org.id, m.user_id, select.value); await reload(); }, "Rol actualizado."));
              return select;
            },
          },
          {
            key: "actions",
            label: "Acciones",
            sortable: false,
            search: false,
            className: "actions",
            render: (m) =>
              canManage
                ? h("button", { class: "button danger small", type: "button", onclick: async () => { if (await confirmDialog({ title: "¿Quitar miembro?", message: `${m.email} perderá el acceso a ${org.name}.`, confirmLabel: "Quitar", danger: true })) guarded(async () => { await api.removeMember(org.id, m.user_id); await reload(); }, "Miembro eliminado."); } }, "Quitar")
                : null,
          },
        ],
      });
      append(clear(detail), [canManage ? h("section", { class: "card" }, h("h2", {}, `Añadir miembro a ${org.name}`), addForm) : null, table.element]);
    } catch (error) {
      clear(detail).append(errorState(error.message));
    }
  }

  const name = field({ id: "org-name", label: "Nombre", required: true, maxlength: "80" });
  const slug = field({ id: "org-slug", label: "Identificador", required: true, maxlength: "40", pattern: "[a-z0-9][a-z0-9-]*", hint: "Solo a-z, 0-9 y guiones." });
  const create = isPlatformAdmin
    ? h(
        "section",
        { class: "card" },
        h("h2", {}, "Crear organización"),
        h(
          "form",
          { class: "inline-form", onsubmit: (event) => { event.preventDefault(); guarded(async () => { await api.createOrganization(name.input.value.trim(), slug.input.value.trim()); name.input.value = ""; slug.input.value = ""; await loadOrganizations(); }, "Organización creada."); } },
          name.element,
          slug.element,
          h("button", { class: "button", type: "submit" }, "Crear"),
        ),
      )
    : null;

  container.append(h("div", { class: "page-body" }, create, listArea, detail));
  await loadOrganizations();
}
