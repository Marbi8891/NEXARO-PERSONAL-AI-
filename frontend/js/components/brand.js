// Marca NEXARO: símbolo geométrico + logotipo tipográfico. Único punto donde se compone.
import { h } from "../dom.js";

export function brand() {
  return h("span", { class: "logo" }, h("img", { src: "/icons/symbol.svg", alt: "", width: "32", height: "32" }), h("span", { class: "wordmark" }, "NEXARO"));
}
