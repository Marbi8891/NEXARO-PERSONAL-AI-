import { api } from "../api.js";
import { clear, h } from "../dom.js";
import { getUser } from "../state.js";

const ROLES = [["owner", "Propietario"], ["admin", "Administrador"], ["member", "Miembro"], ["viewer", "Lector"]];

function roleSelect(id, value) {
  return h("select", { id }, ROLES.map(([key, label]) => h("option", { value: key, selected: key === value }, label)));
}

export async function organizationsView({ container }) {
  const toast = h("p", { class: "toast", role: "status", hidden: true });
  const list = h("div", { class: "card" });
  const detail = h("div", {});
  const isPlatformAdmin = getUser().role === "admin";

  function notify(message, isError = false) {
    toast.hidden = !message;
    toast.textContent = message;
    toast.className = isError ? "toast error" : "toast";
  }
  async function guarded(action, success) {
    try {
      await action();
      notify(success);
    } catch (error) {
      notify(error.message, true);
    }
  }

  async function loadOrganizations() {
    const { organizations } = await api.organizations();
    clear(list).append(h("h2", {}, "Tus organizaciones"));
    if (!organizations.length) list.append(h("p", { class: "empty" }, "No perteneces a ninguna organización."));
    for (const org of organizations) {
      list.append(h("button", { class: "button secondary", type: "button", onclick: () => showMembers(org) }, `${org.name} · ${ROLES.find(([k]) => k === org.role)?.[1] ?? org.role}`), " ");
    }
  }

  async function showMembers(org) {
    const reload = () => showMembers(org);
    const { members } = await api.members(org.id);
    const canManage = org.role === "owner" || org.role === "admin";
    const email = h("input", { id: "member-email", type: "email", required: true });
    const role = roleSelect("member-role", "member");

    const rows = members.map((m) => {
      const select = roleSelect(`role-${m.user_id}`, m.role);
      select.disabled = !canManage;
      select.setAttribute("aria-label", `Rol de ${m.email}`);
      select.addEventListener("change", () => guarded(async () => { await api.setMemberRole(org.id, m.user_id, select.value); await reload(); }, "Rol actualizado."));
      return h("tr", {}, h("td", {}, m.email), h("td", {}, select), h("td", { class: "actions" }, canManage ? h("button", { class: "button danger small", type: "button", onclick: () => guarded(async () => { await api.removeMember(org.id, m.user_id); await reload(); }, "Miembro eliminado.") }, "Quitar") : null));
    });

    clear(detail).append(
      canManage
        ? h("section", { class: "card" }, h("h2", {}, `Añadir miembro a ${org.name}`), h("form", { class: "inline-form", onsubmit: (event) => { event.preventDefault(); guarded(async () => { await api.addMember(org.id, email.value.trim(), role.value); await reload(); }, "Miembro añadido."); } }, h("div", {}, h("label", { for: "member-email" }, "Correo de un usuario existente"), email), h("div", {}, h("label", { for: "member-role" }, "Rol"), role), h("button", { class: "button primary", type: "submit" }, "Añadir")))
        : null,
      h("div", { class: "table-wrap" }, h("table", {}, h("caption", {}, `Miembros de ${org.name}`), h("thead", {}, h("tr", {}, ["Correo", "Rol", "Acciones"].map((t) => h("th", { scope: "col" }, t)))), h("tbody", {}, rows))),
    );
  }

  const name = h("input", { id: "org-name", type: "text", required: true, maxlength: "80" });
  const slug = h("input", { id: "org-slug", type: "text", required: true, maxlength: "40", pattern: "[a-z0-9][a-z0-9-]*" });
  const create = isPlatformAdmin
    ? h("section", { class: "card" }, h("h2", {}, "Crear organización"), h("form", { class: "inline-form", onsubmit: (event) => { event.preventDefault(); guarded(async () => { await api.createOrganization(name.value.trim(), slug.value.trim()); name.value = ""; slug.value = ""; await loadOrganizations(); }, "Organización creada."); } }, h("div", {}, h("label", { for: "org-name" }, "Nombre"), name), h("div", {}, h("label", { for: "org-slug" }, "Identificador (a-z, 0-9, -)"), slug), h("button", { class: "button primary", type: "submit" }, "Crear")))
    : null;

  container.append(h("header", { class: "page-header" }, h("h1", {}, "Organizaciones")), h("div", { class: "page-body" }, toast, create, list, detail));
  try {
    await loadOrganizations();
  } catch (error) {
    notify(error.message, true);
  }
}
