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
const check = async (name, fn) => { await fn(); results.push(name); console.log("ok -", name); };

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
  $(".history-item").click();
  await until(() => document.querySelectorAll(".message").length === 2, "restore");
});
await check("usuario normal no accede a #/admin", async () => {
  location.hash = "#/admin";
  await until(() => location.hash.startsWith("#/chat"), "redirect");
});
await check("organizaciones: usuario normal no ve formulario de creación", async () => {
  location.hash = "#/organizations";
  await until(() => text().includes("Tus organizaciones"), "orgs");
  assert.ok(!text().includes("Crear organización"));
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
