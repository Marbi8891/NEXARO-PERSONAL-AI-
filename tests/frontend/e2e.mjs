import { JSDOM } from "jsdom";
import assert from "node:assert/strict";
import { pathToFileURL } from "node:url";

const nativeFetch = globalThis.fetch;
const BASE = "http://127.0.0.1:8765";
const REPO = process.env.REPO;

async function session() {
  const dom = new JSDOM(`<!doctype html><div id="app"></div>`, { url: BASE + "/", pretendToBeVisual: true });
  const jar = new Map();
  const w = dom.window;
  const wrapped = async (path, opts = {}) => {
    const headers = { ...(opts.headers || {}), Origin: BASE };
    if (jar.size) headers.Cookie = [...jar].map(([k, v]) => `${k}=${v}`).join("; ");
    const res = await nativeFetch(BASE + path, { ...opts, headers });
    for (const c of res.headers.getSetCookie?.() ?? []) {
      const [pair] = c.split(";"); const [k, v] = pair.split("=");
      if (/max-age=0|expires=thu, 01 jan 1970/i.test(c) || v === "") jar.delete(k); else jar.set(k, v);
    }
    return res;
  };
  for (const k of ["document", "window", "location", "localStorage", "history", "Node", "HTMLElement"]) {
    Object.defineProperty(globalThis, k, { value: k === "window" ? w : w[k], configurable: true, writable: true });
  }
  globalThis.fetch = wrapped;
  return { dom, w, jar };
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function until(fn, label) {
  for (let i = 0; i < 100; i++) { try { const v = fn(); if (v) return v; } catch {} await sleep(50); }
  throw new Error("timeout: " + label);
}
const $ = (sel) => document.querySelector(sel);
const text = () => document.body.textContent;
function fill(sel, v) { $(sel).value = v; }
function submit(form) { form.dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true })); }

const results = [];
const noLeaks = () => assert.ok(!/null|undefined/.test(document.body.textContent), "texto null/undefined visible en pantalla");
const check = async (name, fn) => { await fn(); noLeaks(); results.push(name); console.log("ok -", name); };

// --- Usuario normal ---
await session();
const { boot } = await import(pathToFileURL(`${REPO}/frontend/js/app.js`).href);
await boot(document.getElementById("app"));

await check("sin sesión redirige a login", async () => {
  await until(() => $("form.auth-card") && location.hash === "#/login", "login");
});
await check("login con clave incorrecta muestra error y no entra", async () => {
  fill("#email", "user@x.io"); fill("#password", "mala-clave-123456");
  submit($("form.auth-card"));
  await until(() => $(".form-error").textContent.length > 0, "error");
  assert.equal(location.hash, "#/login");
});
await check("login correcto entra al chat con nav sin Administración", async () => {
  fill("#password", "correct-horse-battery");
  submit($("form.auth-card"));
  await until(() => $(".app") && location.hash.startsWith("#/chat"), "chat");
  assert.ok(!text().includes("Administración"));
  assert.ok(text().includes("Organizaciones"));
});
await check("enviar mensaje: respuesta como texto (sin HTML interpretado)", async () => {
  const ta = $("#message"); ta.value = "hola";
  submit($(".composer"));
  await until(() => text().includes("desde el modelo falso"), "answer");
  assert.equal(document.querySelectorAll(".message b").length, 0);
  assert.ok(text().includes("<b>mundo</b>"));
});
await check("historial muestra la conversación y la URL guarda el id", async () => {
  await until(() => document.querySelectorAll(".history-item").length === 1, "history");
  assert.match(location.hash, /^#\/chat\/.+/);
});
await check("nueva conversación vacía el chat", async () => {
  [...document.querySelectorAll("button")].find((b) => b.textContent.includes("Nueva")).click();
  await until(() => $(".welcome"), "welcome");
});
await check("abrir conversación del historial restaura mensajes", async () => {
  await until(() => $(".history-item"), "history item");
  $(".history-item").click();
  await until(() => document.querySelectorAll(".message").length === 2, "restore");
});
await check("panel: cifras reales del usuario, sin sección de plataforma", async () => {
  location.hash = "#/dashboard";
  await until(() => $(".stats") && text().includes("Tu actividad"), "dashboard");
  const stats = Object.fromEntries([...document.querySelectorAll(".stat")].map((s) => [s.querySelector("dt").textContent, s.querySelector("dd").textContent]));
  assert.equal(stats["Conversaciones"], "1");
  assert.equal(stats["Mensajes"], "2");
  assert.ok($(".chart"), "gráfico de actividad");
  assert.equal($(".chart").getAttribute("role"), "img");
  assert.ok(!text().includes("solo administradores"));
  assert.equal(document.querySelectorAll(".recent-list li").length, 1);
});
await check("campana de avisos: se abre, lista el estado real y cierra con Escape", async () => {
  const bell = $(".bell-trigger");
  assert.equal(bell.getAttribute("aria-expanded"), "false");
  bell.click();
  assert.equal(bell.getAttribute("aria-expanded"), "true");
  await until(() => !$("#notifications-panel").hidden && $(".notice-list").children.length > 0, "avisos");
  assert.ok($(".notice-list").textContent.length > 0);
  document.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  assert.equal(bell.getAttribute("aria-expanded"), "false");
});
await check("usuario normal no accede a #/admin", async () => {
  location.hash = "#/admin";
  await until(() => location.hash.startsWith("#/chat"), "redirect");
});
await check("usuario normal no accede a #/security", async () => {
  location.hash = "#/security";
  await until(() => location.hash.startsWith("#/chat"), "redirect");
  assert.ok(!text().includes("Seguridad"), "el enlace Seguridad es solo de administradores");
});
await check("organizaciones: usuario normal no ve formulario de creación", async () => {
  location.hash = "#/organizations";
  await until(() => text().includes("No perteneces a ninguna organización"), "orgs");
  assert.ok(!text().includes("Crear organización"));
});
await check("developer: usuario sin rol de gestión no ve claves y se le explica", async () => {
  location.hash = "#/developer";
  await until(() => text().includes("Sin acceso a claves de API"), "sin acceso");
  assert.ok(!$("#key-name"), "no debe haber formulario de claves");
});
await check("logout vuelve a login", async () => {
  [...document.querySelectorAll("button")].find((b) => b.textContent === "Cerrar sesión").click();
  await until(() => $("form.auth-card") && location.hash === "#/login", "logout");
});
await check("registro: el servidor lo rechaza si está cerrado", async () => {
  location.hash = "#/register";
  await until(() => $("h1")?.textContent === "Solicitar acceso", "register");
  fill("#email", "nuevo@x.io"); fill("#password", "otra-clave-larga-1");
  submit($("form.auth-card"));
  await until(() => $(".form-error").textContent.includes("cerrado"), "closed");
});

// --- Componente de tabla: búsqueda, orden y paginación ---
await check("tabla: paginación, búsqueda, orden y filtro", async () => {
  const { dataTable } = await import(pathToFileURL(`${REPO}/frontend/js/components/table.js`).href);
  const rows = Array.from({ length: 25 }, (_, i) => ({ name: `fila-${String(i + 1).padStart(2, "0")}`, kind: i % 2 ? "par" : "impar" }));
  const table = dataTable({ caption: "Prueba", rows, columns: [{ key: "name", label: "Nombre" }, { key: "kind", label: "Tipo" }], filters: [{ key: "kind", label: "Tipo", options: [["par", "Par"], ["impar", "Impar"]] }] });
  document.body.append(table.element);
  const names = () => [...table.element.querySelectorAll("tbody tr td:first-child")].map((td) => td.textContent);
  const status = () => table.element.querySelector(".table-status").textContent;
  assert.equal(names().length, 10);
  assert.equal(status(), "1–10 de 25");
  [...table.element.querySelectorAll("button")].find((b) => b.textContent === "Siguiente").click();
  assert.equal(status(), "11–20 de 25");
  assert.equal(names()[0], "fila-11");
  const search = table.element.querySelector("input[type=search]");
  search.value = "fila-2"; search.dispatchEvent(new window.Event("input"));
  assert.equal(status(), "1–6 de 6"); // fila-02, fila-20..25
  search.value = ""; search.dispatchEvent(new window.Event("input"));
  const sortButton = [...table.element.querySelectorAll(".th-button")].find((b) => b.textContent.startsWith("Nombre"));
  sortButton.click(); sortButton.click();
  assert.equal(table.element.querySelector("th[aria-sort]").getAttribute("aria-sort"), "descending");
  assert.equal(names()[0], "fila-25");
  const select = table.element.querySelector("select#Prueba-kind");
  select.value = "par"; select.dispatchEvent(new window.Event("change"));
  assert.match(status(), /de 12$/);
  search.value = "no-existe"; search.dispatchEvent(new window.Event("input"));
  assert.equal(status(), "0 resultados");
  assert.ok(table.element.textContent.includes("Ningún resultado"));
  table.element.remove();
});

// --- Administrador (nueva sesión de navegador) ---
await session();
document.getElementById("app") ?? document.body.append(Object.assign(document.createElement("div"), { id: "app" }));
await boot(document.getElementById("app"));
await until(() => $("form.auth-card"), "login admin");
fill("#email", "admin@x.io"); fill("#password", "correct-horse-battery");
submit($("form.auth-card"));
await until(() => $(".app"), "admin app");

await check("admin ve Administración y la usa", async () => {
  assert.ok(text().includes("Administración"));
  location.hash = "#/admin";
  await until(() => text().includes("pend@x.io"), "users");
});
await check("panel de admin: sección de plataforma con cifras reales", async () => {
  location.hash = "#/dashboard";
  await until(() => text().includes("solo administradores"), "admin dashboard");
  assert.ok(text().includes("Cuentas"));
  assert.ok(text().includes("Accesos fallidos"));
  assert.ok(text().includes("Pendientes: 1"));
  location.hash = "#/admin"; // las comprobaciones siguientes parten de Administración
  await until(() => text().includes("pend@x.io"), "users");
});
await check("seguridad: cifras reales de la auditoría y cambio de periodo", async () => {
  location.hash = "#/security";
  await until(() => $(".stats") && text().includes("Accesos fallidos"), "seguridad");
  const stats = () => Object.fromEntries([...document.querySelectorAll(".stat")].map((s) => [s.querySelector("dt").textContent, Number(s.querySelector("dd").textContent)]));
  assert.ok(stats()["Accesos fallidos"] >= 1, "el acceso fallido de la prueba anterior debe aparecer");
  assert.ok($(".chart"), "gráfico de fallos por día");
  assert.ok(text().includes("Orígenes con más accesos fallidos"));
  const select = $("#sec-days");
  select.value = "7"; select.dispatchEvent(new window.Event("change"));
  await until(() => text().includes("Últimos 7 días"), "periodo 7");
  location.hash = "#/admin"; // las comprobaciones siguientes parten de Administración
  await until(() => text().includes("pend@x.io"), "users");
});
await check("admin aprueba un usuario pendiente", async () => {
  const row = [...document.querySelectorAll("tbody tr")].find((r) => r.textContent.includes("pend@x.io"));
  [...row.querySelectorAll("button")].find((b) => b.textContent === "Aprobar").click();
  await until(() => {
    const r = [...document.querySelectorAll("tbody tr")].find((x) => x.textContent.includes("pend@x.io"));
    return r?.textContent.includes("Aprobado");
  }, "approved");
});
await check("admin abre el registro público", async () => {
  [...document.querySelectorAll("button")].find((b) => b.textContent === "Abrir registro").click();
  await until(() => [...document.querySelectorAll("button")].some((b) => b.textContent === "Cerrar registro"), "opened");
});
await check("admin crea un usuario", async () => {
  fill("#new-email", "creado@x.io"); fill("#new-password", "clave-muy-larga-123");
  submit($("form.inline-form"));
  await until(() => text().includes("creado@x.io"), "created");
});
await check("auditoría lista eventos y filtra", async () => {
  [...document.querySelectorAll("[role=tab]")].find((b) => b.textContent === "Auditoría").click();
  await until(() => text().includes("auth.login"), "audit");
});
await check("uso del modelo se muestra", async () => {
  [...document.querySelectorAll("[role=tab]")].find((b) => b.textContent.startsWith("Uso")).click();
  await until(() => text().includes("Coste del mes"), "usage");
});
await check("admin crea organización y añade miembro", async () => {
  location.hash = "#/organizations";
  await until(() => text().includes("Crear organización"), "orgform");
  fill("#org-name", "Acme"); fill("#org-slug", "acme");
  submit(document.querySelectorAll("form.inline-form")[0]);
  await until(() => text().includes("Acme"), "orglist");
  [...document.querySelectorAll("button")].find((b) => b.textContent.startsWith("Acme")).click();
  await until(() => text().includes("Miembros de Acme"), "members");
});
await check("developer: crear clave muestra el secreto una vez, lista solo el prefijo y se revoca", async () => {
  location.hash = "#/developer";
  await until(() => $("#key-name"), "formulario de claves");
  fill("#key-name", "CI");
  $("#key-scopes").value = "chat:write,conversations:read";
  submit([...document.querySelectorAll("form.inline-form")].find((f) => f.querySelector("#key-name")));
  const secretInput = await until(() => $(".secret-card input"), "secreto");
  const secret = secretInput.value;
  assert.match(secret, /^nxr_[A-Za-z0-9_-]{40,}$/);
  const table = $(".data-table");
  assert.ok(table.textContent.includes("CI") && table.textContent.includes("Activa"));
  assert.ok(table.textContent.includes("Chat, Leer conversaciones"), "la tabla muestra los permisos");
  assert.ok(!table.textContent.includes(secret), "la tabla no debe contener la clave completa");
  [...document.querySelectorAll("button")].find((b) => b.getAttribute("aria-label") === "Revocar CI").click();
  await until(() => document.querySelector("dialog"), "confirmación");
  [...document.querySelectorAll("dialog button")].find((b) => b.textContent === "Revocar").click();
  await until(() => $(".data-table").textContent.includes("Revocada"), "revocada");
  assert.ok(!$(".secret-card"), "el secreto no persiste tras recargar la lista");
});
await check("documentos: subir, buscar, preguntar con fuentes y borrar", async () => {
  location.hash = "#/documents";
  await until(() => $("#doc-file"), "formulario de documentos");
  const contenido = "La fianza equivale a dos mensualidades.\n\nEl preaviso es de treinta días.";
  Object.defineProperty($("#doc-file"), "files", { value: [{ name: "contrato.txt", type: "text/plain", text: async () => contenido }] });
  fill("#doc-title", "Contrato");
  submit([...document.querySelectorAll("form.inline-form")].find((f) => f.querySelector("#doc-file")));
  await until(() => $(".data-table")?.textContent.includes("Contrato"), "documento listado");
  assert.ok($(".data-table").textContent.includes("contrato.txt"));
  fill("#doc-question", "fianza");
  [...document.querySelectorAll("button")].find((b) => b.textContent === "Solo buscar").click();
  await until(() => $(".sources")?.textContent.includes("dos mensualidades"), "resultados");
  submit([...document.querySelectorAll("form.inline-form")].find((f) => f.querySelector("#doc-question")));
  await until(() => text().includes("Respuesta") && $(".sources"), "respuesta con fuentes");
  assert.ok($(".sources").textContent.includes("Contrato"));
  [...document.querySelectorAll("button")].find((b) => b.getAttribute("aria-label") === "Borrar Contrato").click();
  await until(() => document.querySelector("dialog"), "confirmación");
  [...document.querySelectorAll("dialog button")].find((b) => b.textContent === "Borrar").click();
  await until(() => !$(".data-table") || !$(".data-table").textContent.includes("contrato.txt"), "borrado");
});
await check("finanzas: alta con importes exactos, resumen, edición, borrado y exportación", async () => {
  const { parseEuros } = await import(pathToFileURL(`${REPO}/frontend/js/views/finance.js`).href);
  assert.equal(parseEuros("12,50"), 1250); assert.equal(parseEuros("12.5"), 1250); assert.equal(parseEuros("0,05"), 5);
  assert.equal(parseEuros("1.234,56"), null); assert.equal(parseEuros("-3"), null); assert.equal(parseEuros("abc"), null);

  location.hash = "#/finance";
  await until(() => $("#exp-desc"), "formulario de gastos");
  fill("#exp-desc", "Hosting VPS"); fill("#exp-cat", "Software"); fill("#exp-amount", "12,10"); fill("#exp-vat", "2,10");
  submit($("#expense-form"));
  const tables = () => [...document.querySelectorAll(".data-table")].map((t) => t.textContent).join(" ");
  await until(() => tables().includes("Hosting VPS"), "gasto listado");
  assert.ok(text().includes("Gasto del mes") && text().includes("12,10"), "el resumen refleja el importe exacto");
  assert.ok(text().includes("software"), "categoría normalizada");
  assert.ok($(".chart-figure"), "gráfico de meses");

  fill("#exp-desc", "x"); fill("#exp-amount", "1.234,56");
  submit($("#expense-form"));
  await until(() => text().includes("Importe no válido"), "importe rechazado en cliente");

  location.hash = "#/finance";
  await until(() => tables().includes("Hosting VPS"), "recarga");
  [...document.querySelectorAll("button")].find((b) => b.getAttribute("aria-label") === "Editar Hosting VPS").click();
  assert.equal($("#exp-amount").value, "12,10");
  fill("#exp-amount", "20"); fill("#exp-vat", "3,47");
  submit($("#expense-form"));
  await until(() => tables().includes("20,00"), "editado");
  assert.match($("a[download]").getAttribute("href"), /\/expenses\/export\.csv\?start=\d{4}-\d{2}-01&end=/);
  [...document.querySelectorAll("button")].find((b) => b.getAttribute("aria-label") === "Borrar Hosting VPS").click();
  await until(() => document.querySelector("dialog"), "confirmación");
  [...document.querySelectorAll("dialog button")].find((b) => b.textContent === "Borrar").click();
  await until(() => text().includes("Sin gastos este mes"), "borrado");
});
await check("chat en streaming: Markdown y bloques de código como nodos seguros", async () => {
  location.hash = "#/chat";
  await until(() => $("#message"), "chat");
  [...document.querySelectorAll("button")].find((b) => b.textContent.includes("Nueva")).click();
  await until(() => $(".welcome"), "welcome");
  $("#message").value = "dame codigo";
  submit($(".composer"));
  await until(() => $(".message.assistant pre.code-block code"), "bloque de código");
  await until(() => !$(".message.generating"), "fin de generación");
  assert.equal($("pre.code-block code").textContent, "print(1)");
  assert.equal($("pre.code-block").getAttribute("data-lang"), "py");
  assert.equal($(".message.assistant strong").textContent, "Hola");
  assert.equal($(".message.assistant .inline-code").textContent, "x");
  assert.equal(document.querySelectorAll(".message b").length, 0, "el HTML del modelo no se interpreta");
  assert.ok(text().includes("<b>x</b>"));
  assert.equal($(".composer button").textContent, "Enviar");
});
await check("botón Detener corta la respuesta, conserva lo generado y deja enviar de nuevo", async () => {
  $("#message").value = "algo lento";
  submit($(".composer"));
  await until(() => $(".composer button").textContent === "Detener", "botón Detener");
  assert.ok($(".message.generating"), "indicador de generación");
  await until(() => $(".message.generating")?.textContent.includes("parte"), "primeros fragmentos");
  $(".composer button").click();
  await until(() => $(".composer button").textContent === "Enviar", "enviar de nuevo");
  assert.ok(text().includes("Respuesta detenida."));
  assert.ok(!$(".message.generating"));
  const last = [...document.querySelectorAll(".message.assistant")].pop();
  assert.ok(last.textContent.includes("parte"), "se conserva lo generado");
  assert.equal($(".composer button").disabled, false);
});
await check("lo detenido queda guardado: al reabrir la conversación está el texto parcial", async () => {
  const id = decodeURIComponent(location.hash.split("/")[2]);
  const { api } = await import(pathToFileURL(`${REPO}/frontend/js/api.js`).href);
  let saved = null;
  for (let i = 0; i < 40 && !saved; i++) {
    const data = await api.conversation(id);
    const last = data.messages.at(-1);
    if (last.role === "assistant" && last.content.includes("parte")) saved = last.content;
    else await sleep(100);
  }
  assert.ok(saved, "respuesta parcial persistida");
});
await check("sesión caducada (cookie borrada) devuelve a login con aviso", async () => {
  globalThis.fetch = async () => new Response(JSON.stringify({ detail: "No autenticado" }), { status: 401 });
  location.hash = "#/chat";
  document.querySelector("button.history-item, .composer")?.dispatchEvent(new window.Event("noop"));
  const { api } = await import(pathToFileURL(`${REPO}/frontend/js/api.js`).href);
  await api.conversations().catch(() => {});
  await until(() => $("form.auth-card") && text().includes("caducado"), "expired");
});

console.log(`\n${results.length} comprobaciones OK`);
process.exit(0);
