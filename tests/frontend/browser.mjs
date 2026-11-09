// Comprobación en Chromium REAL (no jsdom): carga de módulos, CSP, fuente, temas, errores de consola
// y capturas de referencia para docs/design/screenshots. Opcional: necesita `npm install` (≈70 MB).
import chromium from "@sparticuz/chromium";
import assert from "node:assert/strict";
import { mkdirSync } from "node:fs";
import { chromium as playwright } from "playwright-core";

const BASE = "http://127.0.0.1:8765";
const OUT = new URL("../../docs/design/screenshots/", import.meta.url).pathname;
mkdirSync(OUT, { recursive: true });
const executablePath = await chromium.executablePath();
// El paquete desactiva la seguridad web (pensado para AWS Lambda): aquí se quita para probar lo real.
const args = chromium.args.filter((a) => !/disable-web-security|disable-site-isolation|IsolateOrigins/.test(a));
const problems = [];

async function scenario(name, { scheme, viewport }, run) {
  // --single-process: un navegador por escenario.
  const browser = await playwright.launch({ executablePath, args, headless: true });
  const context = await browser.newContext({ colorScheme: scheme, viewport, baseURL: BASE });
  const page = await context.newPage();
  page.on("pageerror", (error) => problems.push(`${name}: ${error.message}`));
  page.on("console", (message) => {
    const text = message.text();
    const expected401 = /401 \(Unauthorized\)/.test(text); // /api/auth/me sin sesión
    if (["error", "warning"].includes(message.type()) && !expected401) problems.push(`${name}: ${text}`);
  });
  try {
    await run(page);
  } finally {
    await browser.close();
  }
  console.log("ok -", name);
}

async function login(page, email) {
  await page.goto("/");
  await page.fill("#email", email);
  await page.fill("#password", "correct-horse-battery");
  await page.click("button[type=submit]");
  await page.waitForSelector(".app");
}

const shots = [
  ["d-light", "light", { width: 1280, height: 800 }],
  ["d-dark", "dark", { width: 1280, height: 800 }],
  ["m-light", "light", { width: 390, height: 780 }],
];
for (const [tag, scheme, viewport] of shots) {
  await scenario(`flujo ${tag}`, { scheme, viewport }, async (page) => {
    await page.goto("/");
    await page.waitForSelector("form.auth-card");
    assert.equal(await page.evaluate(async () => { await document.fonts.ready; return document.fonts.check("14px Inter"); }), true, "Inter no cargó");
    const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
    assert.equal(bg, scheme === "dark" ? "rgb(10, 20, 36)" : "rgb(243, 245, 249)");
    await page.screenshot({ path: `${OUT}${tag}-login.png` });

    await login(page, "admin@x.io");
    await page.fill("#message", "Hola, ¿qué puedes hacer?");
    await page.press("#message", "Enter");
    await page.waitForSelector(".message.assistant:not(:has-text('Pensando'))");
    assert.equal(await page.locator(".message b").count(), 0, "el HTML del modelo debe verse como texto");
    await page.screenshot({ path: `${OUT}${tag}-chat.png` });

    await page.goto("/#/admin");
    await page.waitForSelector("table");
    await page.screenshot({ path: `${OUT}${tag}-admin.png` });
  });
}

await scenario("menú de usuario, perfil y tema", { scheme: "light", viewport: { width: 1280, height: 800 } }, async (page) => {
  await login(page, "user@x.io");
  const trigger = page.getByRole("button", { name: /Menú de usuario/ });
  await trigger.click();
  assert.equal(await trigger.getAttribute("aria-expanded"), "true");
  await page.keyboard.press("Escape");
  assert.equal(await trigger.getAttribute("aria-expanded"), "false");
  assert.equal(await page.evaluate(() => document.activeElement?.className), "user-trigger", "Escape debe devolver el foco al botón");
  await trigger.click();
  await page.getByRole("link", { name: "Perfil" }).click();
  await page.waitForSelector("fieldset.choices");
  await page.getByLabel("Oscuro").check();
  assert.equal(await page.evaluate(() => document.documentElement.dataset.theme), "dark");
  assert.equal(await page.evaluate(() => getComputedStyle(document.body).backgroundColor), "rgb(10, 20, 36)");
  await page.reload();
  await page.waitForSelector(".app");
  assert.equal(await page.evaluate(() => document.documentElement.dataset.theme), "dark", "el tema no persistió");
});

await scenario("tabla y confirmación en administración", { scheme: "light", viewport: { width: 1280, height: 800 } }, async (page) => {
  await login(page, "admin@x.io");
  await page.goto("/#/admin");
  await page.waitForSelector("table");
  await page.getByLabel("Buscar").fill("pend");
  assert.equal(await page.locator("tbody tr").count(), 1);
  await page.getByRole("button", { name: "Correo" }).click();
  assert.equal(await page.locator("th[aria-sort]").getAttribute("aria-sort"), "ascending");
  await page.getByRole("button", { name: "Rechazar" }).click();
  await page.waitForSelector("dialog[open]");
  assert.equal(await page.evaluate(() => document.activeElement?.textContent), "Cancelar", "el foco inicial es la opción segura");
  await page.keyboard.press("Escape");
  await page.waitForSelector("dialog", { state: "detached" });
  assert.ok((await page.locator("tbody tr").first().textContent()).includes("Pendiente"), "cancelar no debe cambiar nada");
  await page.screenshot({ path: `${OUT}d-light-admin-table.png` });
});

await scenario("panel y campana de avisos (escritorio)", { scheme: "light", viewport: { width: 1280, height: 800 } }, async (page) => {
  await login(page, "admin@x.io");
  await page.goto("/#/dashboard");
  await page.waitForSelector(".stats");
  await page.getByRole("button", { name: /^Avisos/ }).click();
  await page.waitForSelector("#notifications-panel:not([hidden])");
  assert.ok((await page.locator(".notice").count()) >= 1, "el admin con una solicitud pendiente debe ver un aviso real");
  await page.screenshot({ path: `${OUT}d-light-dashboard.png` });
  await page.keyboard.press("Escape");
  assert.equal(await page.locator("#notifications-panel").isHidden(), true);
});

await scenario("panel sin desbordamiento horizontal (móvil)", { scheme: "dark", viewport: { width: 390, height: 780 } }, async (page) => {
  await login(page, "admin@x.io");
  await page.goto("/#/dashboard");
  await page.waitForSelector(".stats");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  assert.ok(overflow <= 0, `desbordamiento horizontal: ${overflow}px`);
  await page.screenshot({ path: `${OUT}m-dark-dashboard.png` });
});

await scenario("developer: clave creada con secreto visible una vez", { scheme: "light", viewport: { width: 1280, height: 800 } }, async (page) => {
  await login(page, "admin@x.io");
  const status = await page.evaluate(async () => (await fetch("/api/organizations", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: "Demo Dev", slug: "demo-dev" }) })).status);
  assert.equal(status, 201);
  await page.goto("/#/developer");
  await page.getByLabel("Nombre de la clave").fill("Producción");
  await page.getByRole("button", { name: "Crear clave" }).click();
  await page.waitForSelector(".secret-card");
  assert.match(await page.locator(".secret-card input").inputValue(), /^nxr_/);
  // La captura no debe contener una cadena con forma de clave real, aunque sea de una base de pruebas.
  await page.locator(".secret-card input").evaluate((el) => { el.value = "nxr_EJEMPLO-no-es-una-clave"; });
  await page.screenshot({ path: `${OUT}d-light-developer.png` });
  await page.goto("/#/dashboard");
  await page.goto("/#/developer");
  await page.waitForSelector(".data-table");
  assert.equal(await page.locator(".secret-card").count(), 0, "el secreto no debe volver a mostrarse");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  assert.ok(overflow <= 0);
});

await scenario("seguridad: resumen y sin desbordamiento (escritorio y móvil)", { scheme: "light", viewport: { width: 1280, height: 800 } }, async (page) => {
  await login(page, "admin@x.io");
  for (let i = 0; i < 3; i++) {
    await page.evaluate(() => fetch("/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email: "intruso@x.io", password: "clave-incorrecta-123" }) }));
  }
  await page.goto("/#/security");
  await page.waitForSelector(".chart");
  await page.screenshot({ path: `${OUT}d-light-security.png` });
  await page.setViewportSize({ width: 390, height: 780 });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  assert.ok(overflow <= 0, `desbordamiento horizontal: ${overflow}px`);
});

await scenario("cajón de navegación en móvil", { scheme: "light", viewport: { width: 390, height: 780 } }, async (page) => {
  await login(page, "user@x.io");
  assert.equal(await page.locator("#sidebar").isVisible(), false, "la barra lateral empieza cerrada");
  const open = page.getByRole("button", { name: "Abrir navegación" });
  await open.click();
  await page.locator("#sidebar").waitFor({ state: "visible" }); // la transición dura 200 ms
  await page.screenshot({ path: `${OUT}m-light-drawer.png` });
  await page.keyboard.press("Escape");
  await page.locator("#sidebar").waitFor({ state: "hidden" });
  await open.click();
  await page.locator("#sidebar").waitFor({ state: "visible" });
  await page.getByRole("link", { name: "Organizaciones" }).click();
  await page.waitForSelector("#page-title:has-text('Organizaciones')");
  await page.locator("#sidebar").waitFor({ state: "hidden" }); // navegar cierra el cajón
});

await scenario("navegación por teclado", { scheme: "light", viewport: { width: 1280, height: 800 } }, async (page) => {
  await login(page, "user@x.io");
  await page.goto("/#/organizations"); // sin autoenfoque (el chat enfoca su cuadro de texto al abrirse)
  await page.reload();
  await page.waitForSelector(".app");
  await page.keyboard.press("Tab");
  assert.equal(await page.evaluate(() => document.activeElement?.className), "skip-link");
  await page.keyboard.press("Enter");
  assert.equal(await page.evaluate(() => document.activeElement?.id), "view", "el enlace de salto debe mover el foco al contenido");
});

assert.deepEqual(problems, [], `errores en el navegador:\n${problems.join("\n")}`);
console.log("\nNavegador real: todo OK");
process.exit(0);
