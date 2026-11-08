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

await scenario("selector de tema persiste", { scheme: "light", viewport: { width: 1280, height: 800 } }, async (page) => {
  await login(page, "user@x.io");
  const toggle = page.getByRole("button", { name: /Cambiar tema/ });
  await toggle.click(); // sistema -> claro
  await toggle.click(); // claro -> oscuro
  assert.equal(await page.evaluate(() => document.documentElement.dataset.theme), "dark");
  assert.equal(await page.evaluate(() => getComputedStyle(document.body).backgroundColor), "rgb(10, 20, 36)");
  await page.reload();
  await page.waitForSelector(".app");
  assert.equal(await page.evaluate(() => document.documentElement.dataset.theme), "dark", "el tema no persistió");
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
