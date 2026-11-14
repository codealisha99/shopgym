"""Observations: what the agent sees on each step.

A small DOM walker runs inside the page. It tags every visible interactive element with a
`data-sg-id` (e1, e2, ...) in document order, so the same page state always gives the same ids,
and returns the page as an ordered list of text and element nodes. Python renders that into the
text observation and keeps the element table for actions and tests.
"""

from dataclasses import dataclass, field
from urllib.parse import urlsplit

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

WALK_JS = """
() => {
  document.querySelectorAll('[data-sg-id]').forEach((e) => e.removeAttribute('data-sg-id'));
  const INTERACTIVE = 'a[href],button,input:not([type=hidden]),select,textarea,summary,[role=button],[role=link],[role=checkbox],[role=tab]';
  const clean = (s) => (s || '').replace(/\\s+/g, ' ').trim();
  const isVisible = (el) => {
    if (!el.getClientRects().length) return false;
    const st = getComputedStyle(el);
    return st.visibility !== 'hidden' && st.display !== 'none';
  };
  const labelText = (el) => (el.labels && el.labels.length)
    ? clean(Array.from(el.labels).map((l) => l.innerText).join(' ')) : '';
  const nameOf = (el) => clean(el.getAttribute('aria-label') || labelText(el) ||
    (el.tagName === 'INPUT' && ['submit', 'button', 'reset'].includes(el.type) ? el.value : '') ||
    el.innerText || el.getAttribute('placeholder') || el.getAttribute('title') || '');
  const roleOf = (el) => {
    const explicit = el.getAttribute('role');
    if (explicit) return explicit;
    const tag = el.tagName.toLowerCase();
    if (tag === 'a') return 'link';
    if (tag === 'button' || tag === 'summary') return 'button';
    if (tag === 'select') return 'combobox';
    if (tag === 'textarea') return 'textbox';
    const type = (el.getAttribute('type') || 'text').toLowerCase();
    if (['submit', 'button', 'reset', 'image'].includes(type)) return 'button';
    if (type === 'checkbox') return 'checkbox';
    if (type === 'radio') return 'radio';
    return 'textbox';
  };
  const nodes = [];
  let counter = 0;
  const walk = (parent) => {
    for (const child of parent.childNodes) {
      if (child.nodeType === Node.TEXT_NODE) {
        const t = clean(child.textContent);
        if (t && parent.closest('script,style,noscript') === null) nodes.push({ kind: 'text', text: t, tag: parent.tagName.toLowerCase() });
        continue;
      }
      if (child.nodeType !== Node.ELEMENT_NODE) continue;
      const el = child;
      const tag = el.tagName.toLowerCase();
      if (['script', 'style', 'noscript', 'template', 'label'].includes(tag)) continue;
      if (el.getAttribute('aria-hidden') === 'true' || !isVisible(el)) continue;
      if (el.matches(INTERACTIVE)) {
        counter += 1;
        const id = 'e' + counter;
        el.setAttribute('data-sg-id', id);
        const node = { kind: 'el', id, role: roleOf(el), name: nameOf(el), tag, type: el.getAttribute('type') || '',
          value: el.value !== undefined ? String(el.value) : '', disabled: !!el.disabled,
          checked: !!el.checked, href: el.tagName === 'A' ? el.getAttribute('href') : '' };
        if (tag === 'select') {
          node.options = Array.from(el.options).map((o) => ({ value: o.value, label: clean(o.text), selected: o.selected }));
        }
        nodes.push(node);
        continue;
      }
      if (/^h[1-6]$/.test(tag) && !el.querySelector(INTERACTIVE)) {
        nodes.push({ kind: 'text', text: clean(el.innerText), tag, heading: true });
        continue;
      }
      walk(el);
    }
  };
  walk(document.body);
  return { title: document.title, nodes };
}
"""


@dataclass(frozen=True)
class Element:
    id: str
    role: str
    name: str
    value: str = ""
    tag: str = ""
    type: str = ""
    disabled: bool = False
    checked: bool = False
    href: str = ""
    options: tuple = ()


@dataclass(frozen=True)
class Observation:
    url: str
    title: str
    text: str
    elements: tuple[Element, ...] = field(default_factory=tuple)
    screenshot: bytes = b""
    step: int = 0
    steps_left: int = 0
    instruction: str = ""
    last_error: str | None = None

    def element(self, element_id: str) -> Element | None:
        return next((e for e in self.elements if e.id == element_id), None)

    def find(self, role: str, name: str) -> Element | None:
        """Element with this role and name. An exact name wins; otherwise the first name containing it."""
        needle = name.lower()
        same_role = [e for e in self.elements if e.role == role]
        exact = next((e for e in same_role if e.name.lower() == needle), None)
        return exact or next((e for e in same_role if needle in e.name.lower()), None)


def _render_element(node: dict) -> str:
    bits = [f"[{node['id']}] {node['role']} \"{node['name']}\""]
    if node["role"] in ("textbox", "combobox") and node["value"]:
        bits.append(f"value=\"{node['value']}\"")
    if node["role"] in ("checkbox", "radio"):
        bits.append("checked" if node["checked"] else "unchecked")
    if node["role"] == "link" and node["href"]:
        bits.append(f"-> {node['href']}")
    if node["disabled"]:
        bits.append("disabled")
    if node.get("options"):
        opts = ", ".join(o["label"] for o in node["options"][:12])
        bits.append(f"options=[{opts}]")
    return " ".join(bits)


def _element_from(node: dict) -> Element:
    options = tuple((o["value"], o["label"], o["selected"]) for o in node.get("options", []))
    return Element(id=node["id"], role=node["role"], name=node["name"], value=node["value"], tag=node["tag"],
                   type=node["type"], disabled=node["disabled"], checked=node["checked"], href=node["href"],
                   options=options)


def _render_text(node: dict) -> str:
    if node.get("heading"):
        return f"# {node['text']}"
    return node["text"][:300]


def render_nodes(nodes: list[dict]) -> tuple[str, tuple[Element, ...]]:
    lines, elements = [], []
    for node in nodes:
        if node["kind"] == "el":
            lines.append(_render_element(node))
            elements.append(_element_from(node))
        else:
            lines.append(_render_text(node))
    return "\n".join(lines), tuple(elements)


def _snapshot(page: Page, attempts: int = 3) -> dict:
    """Run the DOM walker. A click that navigates mid-walk destroys the old context, so wait and retry."""
    for attempt in range(attempts):
        try:
            return page.evaluate(WALK_JS)
        except PlaywrightError as exc:
            if "Execution context was destroyed" not in str(exc) or attempt == attempts - 1:
                raise
            page.wait_for_load_state("load", timeout=5000)
    raise AssertionError("unreachable")


def _screenshot(page: Page) -> bytes:
    """A stalled screenshot should not end the episode: the text observation is still valid without it."""
    try:
        return page.screenshot(type="png", animations="disabled", timeout=10000)
    except PlaywrightError:
        return b""


def capture(page: Page, *, step: int = 0, steps_left: int = 0, instruction: str = "",
            last_error: str | None = None, screenshot: bool = True) -> Observation:
    snapshot = _snapshot(page)
    text, elements = render_nodes(snapshot["nodes"])
    parts = urlsplit(page.url)
    url = parts.path + (f"?{parts.query}" if parts.query else "")
    header = f"URL: {url}\nTITLE: {snapshot['title']}\n"
    shot = _screenshot(page) if screenshot else b""
    return Observation(url=url, title=snapshot["title"], text=header + text, elements=elements, screenshot=shot,
                       step=step, steps_left=steps_left, instruction=instruction, last_error=last_error)


def render_for_prompt(obs: Observation) -> str:
    """Text the LLM agents receive: instruction, page text with element ids, last error."""
    parts = [f"Task: {obs.instruction}", obs.text]
    if obs.last_error:
        parts.append(f"Last action failed: {obs.last_error}")
    parts.append(f"Steps left: {obs.steps_left}")
    return "\n\n".join(parts)
