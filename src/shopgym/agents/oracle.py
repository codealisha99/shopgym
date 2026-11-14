"""Scripted oracle: proves every task is solvable through the UI.

Each oracle is a generator that yields Actions. The Controller resolves elements by role and
name on the latest observation, so the script reads like a user, not like a list of ids.
An oracle may read the answer from the page text or from the seed database (the oracle is
privileged; it is a solvability proof, not a model of the agent).
"""

import sqlite3
from collections.abc import Callable, Generator, Mapping
from pathlib import Path
from typing import Any

from shopgym.app.db import connect
from shopgym.env.actions import Action
from shopgym.env.observe import Element, Observation
from shopgym.tasks.registry import Task

Oracle = Callable[["Controller"], Generator[Action, Any, None]]


class OracleError(RuntimeError):
    """An oracle could not find something it expected. This is a bug in the oracle, not the agent."""


class Controller:
    def __init__(self, params: dict[str, Any], initial_db: Path) -> None:
        self.params = params
        self.obs: Observation | None = None
        self._db: sqlite3.Connection = connect(initial_db, readonly=True)

    @property
    def db(self) -> sqlite3.Connection:
        return self._db

    def _find(self, role: str, name: str) -> Element:
        element = self.obs.find(role, name)
        if element is None:
            raise OracleError(f"no {role} named {name!r} on {self.obs.url}")
        return element

    def click(self, role: str, name: str) -> Action:
        return Action(type="click", element=self._find(role, name).id)

    def fill(self, name: str, text: str, submit: bool = False) -> Action:
        return Action(type="type", element=self._find("textbox", name).id, text=text, submit=submit)

    def choose(self, name: str, label: str) -> Action:
        select = self._find("combobox", name)
        options = [o for o in select.options]
        match = next((o for o in options if o[1] == label), None) or \
            next((o for o in options if label.lower() in o[1].lower()), None)
        if match is None:
            raise OracleError(f"option {label!r} not in {name!r}")
        return Action(type="select", element=select.id, value=match[0])

    def check(self, name: str) -> Action:
        element = self._find("checkbox", name)
        if element.checked:
            raise OracleError(f"{name!r} is already checked")
        return Action(type="click", element=element.id)

    def goto(self, path: str) -> Action:
        return Action(type="goto", url=path)

    def finish(self, answer: str | None = None) -> Action:
        return Action(type="finish", answer=answer)

    def product_links(self) -> list[Element]:
        return [e for e in self.obs.elements if e.role == "link" and e.href.startswith("/products/")]

    def close(self) -> None:
        self._db.close()


class OracleAgent:
    name = "oracle"

    def __init__(self, oracles: Mapping[str, Oracle]) -> None:
        self._oracles = oracles
        self._controller: Controller | None = None
        self._gen: Generator[Action, Any, None] | None = None
        self._exhausted = False

    def start(self, task: Task, obs: Observation, initial_db: Path) -> None:
        if task.id not in self._oracles:
            raise OracleError(f"no oracle registered for task {task.id}")
        self._controller = Controller(task.params, initial_db)
        self._controller.obs = obs
        self._gen = self._oracles[task.id](self._controller)
        self._exhausted = False

    def act(self, obs: Observation) -> Action:
        self._controller.obs = obs
        if self._exhausted:
            return self._controller.finish(None)
        try:
            return next(self._gen) if obs.step == 0 else self._gen.send(obs)
        except StopIteration:
            self._exhausted = True
            return self._controller.finish(None)

    def stop(self) -> None:
        if self._controller is not None:
            self._controller.close()
