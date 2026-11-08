// Script clásico y bloqueante a propósito: aplica el tema guardado antes del primer pintado (sin parpadeo).
try {
  const saved = localStorage.getItem("nexaro_theme");
  if (saved === "light" || saved === "dark") document.documentElement.dataset.theme = saved;
} catch {
  // Sin almacenamiento: se usa la preferencia del sistema.
}
