"use strict";
// Códigos de error estables y el texto que ve el usuario: qué pasa y qué hacer.

const ERRORS = Object.freeze({
  DOCKER_NOT_INSTALLED: {
    title: "Docker Desktop no está instalado",
    action: "NEXARO necesita Docker Desktop para ejecutar sus servicios. Descárgalo de https://www.docker.com/products/docker-desktop/, instálalo, ábrelo una vez y pulsa Reintentar.",
  },
  COMPOSE_TOO_OLD: {
    title: "Docker Compose es demasiado antiguo",
    action: "Hace falta Docker Compose 2.20 o posterior. Actualiza Docker Desktop y pulsa Reintentar.",
  },
  DOCKER_NOT_RUNNING: {
    title: "Docker Desktop no está en marcha",
    action: "Abre Docker Desktop desde el menú Inicio, espera a que diga \"Engine running\" y pulsa Reintentar.",
  },
  DOCKER_START_TIMEOUT: {
    title: "Docker Desktop no terminó de arrancar",
    action: "Docker Desktop tarda más de lo esperado. Comprueba que WSL 2 y la virtualización están activadas y pulsa Reintentar.",
  },
  PORT_CONFLICT: {
    title: "El puerto de NEXARO está ocupado",
    action: "Otro programa está usando el puerto del backend. Ciérralo y pulsa Reintentar.",
  },
  NETWORK_FAILED: {
    title: "No se pudo preparar la red de Docker",
    action: "Reinicia Docker Desktop y pulsa Reintentar. Si persiste, revisa los registros.",
  },
  SERVICES_FAILED: {
    title: "Los servicios de NEXARO no arrancaron",
    action: "Revisa los registros. La primera vez se construye la imagen y hace falta conexión a Internet.",
  },
  SERVICES_NOT_STARTED: {
    title: "Los servicios de NEXARO están detenidos",
    action: "El arranque automático de servicios está desactivado. Pulsa Reintentar para arrancarlos.",
  },
  BACKEND_UNHEALTHY: {
    title: "El backend de NEXARO no responde",
    action: "Los contenedores arrancaron pero el backend no contesta. Revisa los registros y pulsa Reintentar.",
  },
  BACKEND_RECOVERY_FAILED: {
    title: "El backend dejó de responder",
    action: "Se intentó recuperarlo varias veces sin éxito. Revisa los registros y pulsa Reintentar.",
  },
  UNEXPECTED: {
    title: "Error inesperado",
    action: "Pulsa Reintentar. Si se repite, abre los registros y comparte el diagnóstico.",
  },
});

function describeError(code) {
  return ERRORS[code] ?? ERRORS.UNEXPECTED;
}

module.exports = { ERRORS, describeError };
