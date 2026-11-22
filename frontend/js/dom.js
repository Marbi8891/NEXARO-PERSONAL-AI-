// Construcción del DOM sin innerHTML: todo texto entra como nodo de texto (nunca se interpreta como HTML).
const PROPERTIES = new Set(["value", "checked", "disabled", "required", "selected", "hidden", "readOnly"]);

export function h(tag, props = {}, ...children) {
  const element = document.createElement(tag);
  for (const [key, value] of Object.entries(props ?? {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") element.className = value;
    else if (key.startsWith("on") && typeof value === "function") {
      element.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (PROPERTIES.has(key)) element[key] = value;
    else element.setAttribute(key, value === true ? "" : String(value));
  }
  append(element, children);
  return element;
}

export function append(parent, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    parent.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return parent;
}

export function clear(element) {
  element.replaceChildren();
  return element;
}

export function formatDate(value) {
  return value ? String(value).replace("T", " ").replace("Z", "").slice(0, 16) : "";
}
