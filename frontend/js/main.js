import { boot } from "./app.js";

boot(document.getElementById("app"));

// El service worker solo se registra en contextos seguros (https o localhost).
if ("serviceWorker" in navigator && (location.protocol === "https:" || location.hostname === "localhost")) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
