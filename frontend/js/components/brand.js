// NEXARO identity: symbol + wordmark. Single source for the application brand.
import { h } from "../dom.js";

export function brand() {
  return h(
    "span",
    { class: "logo", "aria-label": "NEXARO Personal AI" },
    h("img", { src: "/icons/symbol.svg", alt: "", width: "36", height: "36" }),
    h("span", { class: "brand-lockup" },
      h("span", { class: "wordmark" }, "NEXARO"),
      h("span", { class: "brand-descriptor" }, "PERSONAL AI"),
    ),
  );
}
