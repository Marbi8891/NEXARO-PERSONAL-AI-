// Capturas del producto para el README y docs/assets/screenshots (ver docs/assets/README.md).
// Aplicación real (demo_server.py: BD temporal, Gateway real) en Chromium real. Los datos de
// demostración se crean por la API pública, como lo haría un usuario. Ninguna captura muestra texto
// generado por un modelo: el script falla si aparece el marcador del proveedor sustituto.
import chromium from "@sparticuz/chromium";
import assert from "node:assert/strict";
import { mkdirSync } from "node:fs";
import { chromium as playwright } from "playwright-core";

const BASE = `http://127.0.0.1:${process.env.NEXARO_DEMO_PORT ?? "8766"}`;
const OUT = new URL("../../docs/assets/screenshots/", import.meta.url).pathname;
const PASSWORD = "demo-password-not-secret";
const PLACEHOLDER = "Marcador de demostración";
mkdirSync(OUT, { recursive: true });

const executablePath = process.env.CHROMIUM_PATH || (await chromium.executablePath());
const args = chromium.args.filter((a) => !/disable-web-security|disable-site-isolation|IsolateOrigins|single-process/.test(a));
const browser = await playwright.launch({ executablePath, args, headless: true });

async function session(scheme) {
  const context = await browser.newContext({ colorScheme: scheme, viewport: { width: 1280, height: 800 }, deviceScaleFactor: 2, baseURL: BASE });
  const page = await context.newPage();
  await page.goto("/");
  await page.fill("#email", "admin@example.com");
  await page.fill("#password", PASSWORD);
  await page.click("button[type=submit]");
  await page.waitForSelector(".app");
  return { context, page };
}

async function api(page, method, path, data) {
  const response = await page.request.fetch(path, { method, data, headers: { Origin: BASE } });
  assert.ok(response.ok(), `${method} ${path} -> ${response.status()} ${await response.text()}`);
  return response.json();
}

async function seed(page) {
  const { organization } = await api(page, "POST", "/api/organizations", { name: "Equipo de Plataforma", slug: "plataforma" });
  const org = organization?.id ?? (await api(page, "GET", "/api/organizations")).organizations[0].id;
  const documents = [
    ["Guía de despliegue con Docker", "El backend publica solo 127.0.0.1:8001. Ollama se alcanza por la red privada de Docker y no publica puertos. Para actualizar se reconstruye solo el servicio backend conservando el volumen de datos. Nunca se ejecuta docker compose down -v."],
    ["Política de copias de seguridad", "Se hace una copia verificada cada día y antes de cada actualización. Las copias se guardan fuera del repositorio y del volumen. Una restauración se ensaya primero en un volumen nuevo."],
    ["Checklist de seguridad de la API", "Validar el origen en las rutas que modifican estado. Limitar intentos de acceso por cuenta y por IP. Guardar solo el hash de las claves de API y mostrarlas una vez. Registrar cada denegación en la auditoría."],
  ];
  for (const [title, content] of documents) {
    await api(page, "POST", `/api/organizations/${org}/documents`, { title, content });
  }
  await api(page, "POST", "/api/agents/custom", {
    name: "Revisor de código Python", description: "Revisa cambios buscando errores, tipos y tests que faltan.",
    category: "desarrollo", base_agent: "developer",
    instructions: "Revisa el código paso a paso. Señala primero los errores de corrección y después el estilo. Propón tests concretos.",
  });
  await api(page, "POST", "/api/agents/custom", {
    name: "Analista de incidentes", description: "Ordena la cronología de un incidente y propone medidas.",
    category: "seguridad", base_agent: "security",
    instructions: "Reconstruye la cronología, separa hechos de hipótesis y termina con acciones priorizadas.",
  });
  const catalogue = await api(page, "GET", "/api/prompt-catalogue");
  const items = catalogue.prompts ?? catalogue.items ?? catalogue;
  for (const item of items.slice(0, 4)) {
    await api(page, "POST", `/api/organizations/${org}/prompts/install`, { catalogue_id: item.id });
  }
  for (const message of [
    "Revisa la configuración de Docker Compose del backend",
    "Resume la política de copias de seguridad",
    "¿Qué comprueba el checklist de seguridad de la API?",
  ]) {
    await api(page, "POST", "/api/chat", { message });
  }
}

async function shot(page, name, { hash, ready, before }) {
  if (hash) await page.goto(`/#${hash}`);
  if (ready) await page.waitForSelector(ready);
  if (before) await before(page);
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(400);
  const text = await page.evaluate(() => document.body.innerText);
  assert.ok(!text.includes(PLACEHOLDER), `${name}: la captura mostraría texto del proveedor sustituto`);
  await page.screenshot({ path: `${OUT}${name}.png` });
  console.log("ok -", name);
}

const light = await session("light");
await seed(light.page);
await shot(light.page, "dashboard", { hash: "/dashboard", ready: ".page-body" });
await shot(light.page, "agents", {
  hash: "/agents",
  ready: "table",
  // La lista de agentes queda debajo del formulario: se encuadra la tabla.
  before: (page) => page.locator("table").first().evaluate((el) => el.closest("section, .card, div").scrollIntoView({ block: "start" })),
});
await shot(light.page, "documents", { hash: "/documents", ready: ".page-body table, .page-body .card" });
await shot(light.page, "prompts", { hash: "/prompts", ready: ".page-body" });
await shot(light.page, "security", { hash: "/security", ready: ".page-body" });
const tab = (label) => async (page) => {
  await page.getByRole("tab", { name: label }).click();
  await page.waitForTimeout(600);
};
await shot(light.page, "model-management", { hash: "/admin", ready: "[role=tablist]", before: tab("Modelos") });
await shot(light.page, "operations", { hash: "/admin", ready: "[role=tablist]", before: tab("Operaciones") });
await light.context.close();

const dark = await session("dark");
await shot(dark.page, "chat-dark", {
  hash: "/chat",
  ready: "#message",
  before: async (page) => {
    await page.getByRole("button", { name: /Nueva conversación/ }).click();
    await page.waitForTimeout(300);
  },
});
await shot(dark.page, "dashboard-dark", { hash: "/dashboard", ready: ".page-body" });
await dark.context.close();
await browser.close();
