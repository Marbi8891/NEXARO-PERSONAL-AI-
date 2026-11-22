"use strict";
// Pantalla de arranque: muestra el estado que envía el proceso principal. Sin Node ni acceso a
// archivos; solo usa el puente `window.nexaroDesktop` (preload). El DOM se construye sin innerHTML.

const LABELS = {
  windows: "Windows",
  compose: "Docker Compose",
  docker: "Docker Desktop",
  ollama: "Ollama",
  ports: "Puertos",
  services: "Servicios",
  backend: "Backend (API)",
  database: "Base de datos",
  agents: "Agent Runtime",
  ai: "IA (modelo)",
};
const ICONS = { ok: "✓", warn: "!", fail: "✕", pending: "…", skip: "–" };

const bridge = window.nexaroDesktop;
const $ = (id) => document.getElementById(id);

function render(snapshot) {
  if (!snapshot) return;
  $("status").dataset.state = snapshot.state;
  $("state-label").textContent = snapshot.state;
  $("message").textContent = snapshot.message;
  const detail = $("detail");
  detail.hidden = !snapshot.detail;
  detail.textContent = snapshot.detail ?? "";

  const list = $("checks");
  list.replaceChildren(
    ...Object.entries(snapshot.checks ?? {}).map(([name, check]) => {
      const li = document.createElement("li");
      const icon = document.createElement("span");
      icon.className = "icon";
      icon.dataset.status = check.status;
      icon.textContent = ICONS[check.status] ?? "?";
      const label = document.createElement("span");
      label.className = "name";
      label.textContent = LABELS[name] ?? name;
      const text = document.createElement("span");
      text.textContent = check.message;
      li.append(icon, label, text);
      return li;
    }),
  );
  $("retry").hidden = !["ERROR", "STOPPED"].includes(snapshot.state);
  $("open-app").hidden = snapshot.state !== "DEGRADED";
}

$("retry").addEventListener("click", () => bridge.retry());
$("open-logs").addEventListener("click", () => bridge.openLogs());
$("open-app").addEventListener("click", () => bridge.openApp());

bridge.onState(render);
bridge.getState().then(render);
