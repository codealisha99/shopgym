"""Load the declarative task file and bind each task to its setup, checker and oracle."""

import functools
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from shopgym.env.episodes import SetupFn
from shopgym.tasks.checkers import CHECKERS, CheckContext, Verdict
from shopgym.tasks.setups import SETUPS

TASKS_FILE = Path(__file__).parent / "tasks.yaml"
TIERS = ("easy", "medium", "hard")


@dataclass(frozen=True)
class Task:
    id: str
    tier: str
    instruction: str
    start_url: str
    seed: int
    max_steps: int
    checker: str
    params: dict = field(default_factory=dict)
    setup: str | None = None
    setup_params: dict = field(default_factory=dict)

    def make_setup(self) -> SetupFn | None:
        if self.setup is None:
            return None
        return functools.partial(SETUPS[self.setup], **self.setup_params)

    def evaluate(self, ctx: CheckContext) -> Verdict:
        return CHECKERS[self.checker](ctx, **self.params)


def _task(raw: dict[str, Any], default_seed: int) -> Task:
    task = Task(
        id=raw["id"], tier=raw["tier"], instruction=raw["instruction"].strip(), start_url=raw["start_url"],
        seed=raw.get("seed", default_seed), max_steps=raw.get("max_steps", 25), checker=raw["checker"],
        params=raw.get("params", {}), setup=raw.get("setup"), setup_params=raw.get("setup_params", {}))
    if task.tier not in TIERS or task.checker not in CHECKERS or (task.setup and task.setup not in SETUPS):
        raise ValueError(f"task {task.id} references an unknown tier, checker or setup")
    return task


def load_tasks(path: Path = TASKS_FILE) -> dict[str, Task]:
    raw = yaml.safe_load(path.read_text())
    tasks = [_task(t, raw.get("default_seed", 7)) for t in raw["tasks"]]
    ids = [t.id for t in tasks]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate task ids")
    return {t.id: t for t in tasks}


def get_task(task_id: str) -> Task:
    tasks = load_tasks()
    if task_id not in tasks:
        raise KeyError(f"unknown task {task_id!r}")
    return tasks[task_id]
