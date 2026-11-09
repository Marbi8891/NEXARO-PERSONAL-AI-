// Documentos de una organización: cargar texto, buscar y preguntar con fuentes.
// Leen todos los miembros; suben y borran propietarios, administradores y miembros (lo impone el servidor).
import { api } from "../api.js";
import { confirmDialog } from "../components/dialog.js";
import { field } from "../components/form.js";
import { emptyState, errorState, loadingState } from "../components/states.js";
import { dataTable } from "../components/table.js";
import { toast } from "../components/toast.js";
import { append, clear, formatDate, h } from "../dom.js";

const ACCEPT = ".pdf,.txt,.md,.markdown,.csv,.json,.log,application/pdf,text/plain,text/markdown,text/csv,application/json";
const isPdf = (file) => file.type === "application/pdf" || /\.pdf$/i.test(file.name);
const canWrite = (org) => ["owner", "admin", "member"].includes(org.role);
const kb = (bytes) => (bytes < 1024 ? `${bytes} B` : `${(bytes / 1024).toFixed(1)} KB`);

export async function documentsView({ container, shell }) {
  shell.setTitle("Documentos");
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
    body.append(
      emptyState({
        title: "Sin organizaciones",
        text: "Los documentos pertenecen a una organización. Pide que te añadan a una o crea una desde Organizaciones.",
        action: h("a", { class: "button secondary", href: "#/organizations" }, "Ver organizaciones"),
      }),
    );
    return;
  }

  const content = h("div", { class: "stack" });
  const picker = field({ id: "doc-org", label: "Organización", options: organizations.map((o) => [o.id, o.name]), value: organizations[0].id });
  const current = () => organizations.find((o) => o.id === picker.input.value);
  picker.input.addEventListener("change", () => show(current()));
  append(body, [organizations.length > 1 ? h("section", { class: "card" }, picker.element) : null, content]);
  await show(organizations[0]);

  async function show(org) {
    clear(content).append(loadingState());
    try {
      const { documents, limits } = await api.documents(org.id);
      const reload = () => show(org);

      const upload = canWrite(org) ? uploadCard(org, documents.length, limits, reload) : null;
      const table = dataTable({
        caption: `Documentos de ${org.name}`,
        rows: documents,
        empty: { title: "Aún no hay documentos", text: canWrite(org) ? "Sube el primero con el formulario de arriba." : "Un propietario, administrador o miembro puede subirlos." },
        columns: [
          { key: "title", label: "Título" },
          { key: "source", label: "Archivo", value: (d) => d.source ?? "—" },
          { key: "size_bytes", label: "Tamaño", value: (d) => kb(d.size_bytes) },
          { key: "chunk_count", label: "Fragmentos" },
          { key: "created_at", label: "Subido", value: (d) => formatDate(d.created_at) },
          { key: "created_by_email", label: "Por", value: (d) => d.created_by_email ?? "—" },
          {
            key: "actions",
            label: "Acciones",
            sortable: false,
            search: false,
            className: "actions",
            render: (d) =>
              canWrite(org)
                ? h("button", { class: "button danger small", type: "button", "aria-label": `Borrar ${d.title}`, onclick: async () => {
                    if (!(await confirmDialog({ title: "¿Borrar documento?", message: `«${d.title}» dejará de aparecer en búsquedas y respuestas.`, confirmLabel: "Borrar", danger: true }))) return;
                    try {
                      await api.deleteDocument(org.id, d.id);
                      toast("Documento borrado.");
                      await reload();
                    } catch (error) {
                      toast(error.message, { error: true });
                    }
                  } }, "Borrar")
                : null,
          },
        ],
      });
      append(clear(content), [upload, table.element, documents.length > 0 ? askCard(org) : null]);
    } catch (error) {
      clear(content).append(errorState(error.message, { onRetry: () => show(org) }));
    }
  }

  function uploadCard(org, count, limits, reload) {
    const file = field({ id: "doc-file", label: "Archivo", type: "file", accept: ACCEPT, hint: `PDF con texto (no escaneado), .txt, .md, .csv, .json o .log. Máximo ${limits.max_chars.toLocaleString("es-ES")} caracteres; ${count} de ${limits.max_documents} documentos.` });
    const title = field({ id: "doc-title", label: "Título", required: true, maxlength: "200" });
    file.input.addEventListener("change", () => {
      const chosen = file.input.files[0];
      if (chosen && !title.input.value) title.input.value = chosen.name.replace(/\.[^.]+$/, "");
    });
    return h(
      "section",
      { class: "card" },
      h("h2", {}, "Subir documento"),
      h(
        "form",
        {
          class: "inline-form",
          onsubmit: async (event) => {
            event.preventDefault();
            const chosen = file.input.files[0];
            if (!chosen) return toast("Elige un archivo.", { error: true });
            try {
              const name = title.input.value.trim();
              const created = isPdf(chosen)
                ? await api.uploadPdf(org.id, chosen, name)
                : await api.createDocument(org.id, { title: name, content: await chosen.text(), source: chosen.name, mime_type: chosen.type || null });
              toast(`Documento subido (${created.chunk_count} fragmentos).`);
              await reload();
            } catch (error) {
              toast(error.message, { error: true });
            }
          },
        },
        file.element,
        title.element,
        h("button", { class: "button", type: "submit" }, "Subir"),
      ),
    );
  }

  function askCard(org) {
    const question = field({ id: "doc-question", label: "Pregunta o búsqueda", required: true, maxlength: "2000", hint: "Busca en los documentos de la organización; «Preguntar» además redacta una respuesta con el modelo y cita las fuentes." });
    const output = h("div", { class: "stack", "aria-live": "polite" });
    const buttons = [];
    const run = async (mode) => {
      const text = question.input.value.trim();
      if (!text) return;
      buttons.forEach((b) => (b.disabled = true));
      clear(output).append(loadingState());
      try {
        if (mode === "ask") {
          const { answer, sources } = await api.askDocuments(org.id, text);
          append(clear(output), [h("div", { class: "card" }, h("h3", {}, "Respuesta"), h("p", { class: "answer" }, answer)), sourcesList(sources)]);
        } else {
          const { results } = await api.searchDocuments(org.id, text);
          append(clear(output), [results.length ? sourcesList(results) : h("p", { class: "hint" }, "Sin coincidencias.")]);
        }
      } catch (error) {
        clear(output).append(errorState(error.message));
      } finally {
        buttons.forEach((b) => (b.disabled = false));
      }
    };
    buttons.push(
      h("button", { class: "button", type: "submit" }, "Preguntar"),
      h("button", { class: "button secondary", type: "button", onclick: () => run("search") }, "Solo buscar"),
    );
    return h(
      "section",
      { class: "card" },
      h("h2", {}, "Preguntar a tus documentos"),
      h("form", { class: "inline-form", onsubmit: (event) => { event.preventDefault(); run("ask"); } }, question.element, ...buttons),
      output,
    );
  }
}

function sourcesList(items) {
  if (items.length === 0) return h("p", { class: "hint" }, "Sin fuentes.");
  return h(
    "section",
    { class: "card" },
    h("h3", {}, "Fuentes"),
    h("ol", { class: "sources" }, items.map((s) => h("li", {}, h("strong", {}, s.title), h("span", { class: "hint" }, ` · fragmento ${s.ordinal + 1}`), h("p", {}, s.snippet)))),
  );
}
