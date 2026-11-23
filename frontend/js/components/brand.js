// NEXARO Enterprise wordmark and symbol lockup.
import { h } from "../dom.js";

export function brand() {
  return h(
    "span",
    { class: "logo", "aria-label": "NEXARO Intelligence Platform" },
    h("img", { src: "/icons/symbol.svg", alt: "", width: "34", height: "34" }),
    h("span", { class: "brand-lockup" },
      h("span", { class: "wordmark" }, "NEXARO"),
      h("span", { class: "brand-descriptor" }, "INTELLIGENCE PLATFORM"),
    ),
  );
}
