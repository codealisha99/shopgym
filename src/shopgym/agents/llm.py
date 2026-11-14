"""LLM agents. One provider module, chosen by env vars:

  SHOPGYM_PROVIDER=anthropic (default)  uses the Anthropic SDK, ANTHROPIC_API_KEY, SHOPGYM_MODEL
                                        (default claude-sonnet-5-5)
  SHOPGYM_PROVIDER=openai               any OpenAI-compatible server: SHOPGYM_BASE_URL (for example
                                        http://localhost:11434/v1 for Ollama), SHOPGYM_MODEL, and
                                        SHOPGYM_API_KEY if the server needs one

Modes: "text" sends the element list only; "screenshot" also sends the page image.
Tests use ScriptedProvider, which replays canned replies, so the agent loop runs with no keys.
"""

import base64
import json
import os
from collections.abc import Iterable
from typing import Any, Protocol

from shopgym.env.observe import Observation, render_for_prompt
from shopgym.tasks.registry import Task

DEFAULT_MODEL = "claude-sonnet-5-5"
HISTORY_TURNS = 6

SYSTEM_PROMPT = """You are operating a web browser on an online shop (Ridgeline Supply) to complete one task.
Each turn you see the page as text. Interactive elements have ids like [e12]; use only ids from the current page.
Reply with exactly one JSON action object and nothing else. Allowed actions:
  {"type":"click","element":"e12"}
  {"type":"type","element":"e5","text":"hello","submit":false}   (replaces the field value; submit=true presses Enter)
  {"type":"select","element":"e7","value":"price_asc"}           (value or visible label)
  {"type":"press","key":"Enter"}
  {"type":"scroll","direction":"down","amount":600}
  {"type":"back"}
  {"type":"goto","url":"/orders"}                                  (a path on this site)
  {"type":"finish","answer":"..."}                                 (call when the task is done; put any requested answer here)
Do only what the task asks. Do not change anything else."""


class Provider(Protocol):
    def complete(self, system: str, messages: list[dict[str, Any]]) -> str: ...


class AnthropicProvider:
    def __init__(self, model: str | None = None, max_tokens: int = 1024) -> None:
        from anthropic import Anthropic  # reads ANTHROPIC_API_KEY from the environment

        self._client = Anthropic()
        self._model = model or os.environ.get("SHOPGYM_MODEL", DEFAULT_MODEL)
        self._max_tokens = max_tokens

    def complete(self, system: str, messages: list[dict[str, Any]]) -> str:
        response = self._client.messages.create(model=self._model, max_tokens=self._max_tokens,
                                                system=system, messages=messages)
        return "".join(block.text for block in response.content if block.type == "text")


def _openai_content(content: Any) -> Any:
    if isinstance(content, str):
        return content
    parts = []
    for block in content:
        if block["type"] == "text":
            parts.append({"type": "text", "text": block["text"]})
        else:
            url = f"data:image/png;base64,{block['source']['data']}"
            parts.append({"type": "image_url", "image_url": {"url": url}})
    return parts


class OpenAICompatProvider:
    def __init__(self, base_url: str | None = None, model: str | None = None, api_key: str | None = None) -> None:
        self._base = (base_url or os.environ["SHOPGYM_BASE_URL"]).rstrip("/")
        self._model = model or os.environ.get("SHOPGYM_MODEL", DEFAULT_MODEL)
        self._key = api_key or os.environ.get("SHOPGYM_API_KEY", "")

    def complete(self, system: str, messages: list[dict[str, Any]]) -> str:
        import httpx

        payload = {"model": self._model, "messages": [{"role": "system", "content": system}] +
                   [{"role": m["role"], "content": _openai_content(m["content"])} for m in messages]}
        headers = {"Authorization": f"Bearer {self._key}"} if self._key else {}
        resp = httpx.post(f"{self._base}/chat/completions", json=payload, headers=headers, timeout=120)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"] or ""


class ScriptedProvider:
    """Replays canned replies. Used by tests and by anything that must run offline."""

    def __init__(self, replies: Iterable[str]) -> None:
        self._replies = iter(replies)

    def complete(self, system: str, messages: list[dict[str, Any]]) -> str:
        try:
            return next(self._replies)
        except StopIteration as exc:
            raise RuntimeError("ScriptedProvider ran out of replies") from exc


def provider_from_env() -> Provider:
    kind = os.environ.get("SHOPGYM_PROVIDER", "anthropic")
    if kind == "openai":
        return OpenAICompatProvider()
    if kind == "anthropic":
        return AnthropicProvider()
    raise ValueError(f"SHOPGYM_PROVIDER must be 'anthropic' or 'openai', got {kind!r}")


def parse_reply(reply: str) -> Any:
    """Pull the first JSON object out of the reply. Unparseable text is passed on; the env reports it."""
    start = reply.find("{")
    if start >= 0:
        try:
            obj, _ = json.JSONDecoder().raw_decode(reply[start:])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
    return reply.strip()


class LLMAgent:
    name = "llm"

    def __init__(self, provider: Provider, mode: str = "text") -> None:
        if mode not in ("text", "screenshot"):
            raise ValueError("mode must be 'text' or 'screenshot'")
        self._provider = provider
        self._mode = mode
        self._history: list[tuple[str, str]] = []

    def start(self, task: Task, obs: Observation, initial_db) -> None:
        self._history = []

    def act(self, obs: Observation) -> Any:
        text = render_for_prompt(obs)
        content: list[dict[str, Any]] = [{"type": "text", "text": text}]
        if self._mode == "screenshot":
            image = base64.standard_b64encode(obs.screenshot).decode()
            content.insert(0, {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": image}})
        messages = []
        for past_user, past_reply in self._history[-HISTORY_TURNS:]:
            messages += [{"role": "user", "content": past_user}, {"role": "assistant", "content": past_reply}]
        messages.append({"role": "user", "content": content})
        reply = self._provider.complete(SYSTEM_PROMPT, messages)
        self._history.append((text, reply))
        return parse_reply(reply)

    def stop(self) -> None:
        return None
