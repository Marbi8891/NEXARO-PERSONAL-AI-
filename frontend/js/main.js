import { boot } from "./app.js";

boot(document.getElementById("app"));

// isSecureContext: HTTPS (Tailscale Serve), localhost y 127.0.0.1. En HTTP por IP de red no hay PWA.
if ("serviceWorker" in navigator && window.isSecureContext) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
