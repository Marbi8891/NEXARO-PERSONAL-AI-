// Tema: "system" (preferencia del sistema), "light" o "dark". Se guarda por navegador.
const KEY = "nexaro_theme";
const ORDER = ["system", "light", "dark"];
export const LABELS = { system: "Sistema", light: "Claro", dark: "Oscuro" };

export function getTheme() {
  try {
    const saved = localStorage.getItem(KEY);
    return ORDER.includes(saved) ? saved : "system";
  } catch {
    return "system";
  }
}

export function setTheme(mode) {
  const root = document.documentElement;
  if (mode === "system") delete root.dataset.theme;
  else root.dataset.theme = mode;
  try {
    if (mode === "system") localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, mode);
  } catch {
    // Sin almacenamiento: el cambio vale solo para esta sesión.
  }
}

export function nextTheme(mode) {
  return ORDER[(ORDER.indexOf(mode) + 1) % ORDER.length];
}
