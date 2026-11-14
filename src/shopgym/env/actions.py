"""Action space: parsed and validated at the boundary, then executed on the page.

  click    {"type":"click","element":"e12"}  or  {"type":"click","x":120,"y":340}
  type     {"type":"type","element":"e5","text":"abc","submit":false}   (replaces the field value)
  press    {"type":"press","key":"Enter"}
  scroll   {"type":"scroll","direction":"down","amount":600}
  select   {"type":"select","element":"e7","value":"price_asc"}        (matches value or label)
  back     {"type":"back"}
  goto     {"type":"goto","url":"/orders"}                              (same-site paths only)
  finish   {"type":"finish","answer":"..."}
"""

import json
import re
from dataclasses import dataclass
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

ACTION_TYPES = ("click", "type", "press", "scroll", "select", "back", "goto", "finish")
ELEMENT_ID_RE = re.compile(r"^e\d{1,5}$")
MAX_TEXT = 500


class ActionError(ValueError):
    """The action is malformed or cannot be applied to the current page."""


@dataclass(frozen=True)
class Action:
    type: str
    element: str | None = None
    x: float | None = None
    y: float | None = None
    text: str | None = None
    submit: bool = False
    key: str | None = None
    direction: str | None = None
    amount: int | None = None
    value: str | None = None
    url: str | None = None
    answer: str | None = None


def _need_element(raw: dict) -> str:
    element = raw.get("element")
    if not isinstance(element, str) or not ELEMENT_ID_RE.match(element):
        raise ActionError(f"'element' must look like e12, got {element!r}")
    return element


def _need_str(raw: dict, key: str, *, max_len: int = MAX_TEXT) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or len(value) > max_len:
        raise ActionError(f"'{key}' must be a string up to {max_len} characters")
    return value


def _parse_click(raw: dict) -> Action:
    if "element" in raw:
        return Action(type="click", element=_need_element(raw))
    x, y = raw.get("x"), raw.get("y")
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (x, y)):
        raise ActionError("click needs 'element' or numeric 'x' and 'y'")
    if not (0 <= x <= 1280 and 0 <= y <= 800):
        raise ActionError("click coordinates must fall inside the 1280x800 viewport")
    return Action(type="click", x=float(x), y=float(y))


def _parse_goto(raw: dict) -> Action:
    url = _need_str(raw, "url", max_len=300)
    if not url.startswith("/") or url.startswith("//") or "\\" in url or "\n" in url:
        raise ActionError("goto takes a path on this site, such as /orders")
    return Action(type="goto", url=url)


def _parse_scroll(raw: dict) -> Action:
    direction = raw.get("direction", "down")
    if direction not in ("up", "down"):
        raise ActionError("scroll direction must be 'up' or 'down'")
    amount = raw.get("amount", 600)
    if not isinstance(amount, int) or not 1 <= amount <= 5000:
        raise ActionError("scroll amount must be an integer from 1 to 5000")
    return Action(type="scroll", direction=direction, amount=amount)


_PARSERS = {
    "click": _parse_click,
    "goto": _parse_goto,
    "scroll": _parse_scroll,
    "type": lambda r: Action(type="type", element=_need_element(r), text=_need_str(r, "text"),
                             submit=bool(r.get("submit", False))),
    "press": lambda r: Action(type="press", key=_need_str(r, "key", max_len=30)),
    "select": lambda r: Action(type="select", element=_need_element(r), value=_need_str(r, "value")),
    "back": lambda r: Action(type="back"),
    "finish": lambda r: Action(type="finish", answer=_need_str(r, "answer", max_len=2000)
                               if r.get("answer") is not None else None),
}


def parse_action(raw: Any) -> Action:
    """Accept a dict or a JSON string. Anything else is rejected before touching the browser."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ActionError(f"action is not valid JSON: {exc.msg}") from exc
    if not isinstance(raw, dict):
        raise ActionError("action must be a JSON object")
    kind = raw.get("type")
    if kind not in _PARSERS:
        raise ActionError(f"unknown action type {kind!r}; use one of {', '.join(ACTION_TYPES)}")
    return _PARSERS[kind](raw)


def _locate(page: Page, element: str):
    locator = page.locator(f'[data-sg-id="{element}"]')
    if locator.count() == 0:
        raise ActionError(f"no element {element} on this page; use an id from the current observation")
    return locator.first


def _select(page: Page, action: Action) -> None:
    locator = _locate(page, action.element)
    try:
        locator.select_option(value=action.value)
    except PlaywrightError:
        locator.select_option(label=action.value)


def _press(page: Page, key: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9+ ]{1,30}", key):
        raise ActionError(f"unsupported key {key!r}")
    page.keyboard.press(key)


def _go_back(page: Page) -> None:
    if page.go_back() is None:
        raise ActionError("there is no earlier page in this browser history")


def apply_action(page: Page, action: Action, base_url: str) -> None:
    """Perform a non-terminal action. Raises ActionError for problems the agent can fix."""
    if action.type == "click":
        if action.element is not None:
            _locate(page, action.element).click(timeout=5000)
        else:
            page.mouse.click(action.x, action.y)
    elif action.type == "type":
        locator = _locate(page, action.element)
        locator.fill(action.text, timeout=5000)
        if action.submit:
            locator.press("Enter")
    elif action.type == "press":
        _press(page, action.key)
    elif action.type == "scroll":
        sign = 1 if action.direction == "down" else -1
        page.mouse.wheel(0, sign * action.amount)
    elif action.type == "select":
        _select(page, action)
    elif action.type == "back":
        _go_back(page)
    elif action.type == "goto":
        page.goto(base_url + action.url, wait_until="load")
    settle(page)


def settle(page: Page) -> None:
    """Wait for navigation to finish. Playwright's click already waits for navigations it started."""
    try:
        page.wait_for_load_state("load", timeout=5000)
    except PlaywrightError:
        pass
