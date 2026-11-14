"""Baseline agents. They should score about zero: a checker that passes them has a false positive."""

import random

from shopgym.env.actions import Action
from shopgym.env.observe import Observation
from shopgym.tasks.registry import Task

WORDS = ["hello", "test", "order", "42", "lorem ipsum", "x", "help"]


class NoOpAgent:
    """Does nothing and finishes with an empty answer."""

    name = "noop"

    def start(self, task: Task, obs: Observation, initial_db) -> None:
        return None

    def act(self, obs: Observation) -> Action:
        return Action(type="finish", answer="")

    def stop(self) -> None:
        return None


class RandomAgent:
    """Random clicks, typing, keys, scrolling and an occasional random finish. Seeded for replay."""

    name = "random"

    def __init__(self, seed: int = 0) -> None:
        self._rng = random.Random(seed)

    def start(self, task: Task, obs: Observation, initial_db) -> None:
        return None

    def act(self, obs: Observation) -> Action:
        rng = self._rng
        roll = rng.random()
        clickable = [e for e in obs.elements if not e.disabled]
        if roll < 0.04:
            return Action(type="finish", answer=str(rng.randint(0, 99)))
        if roll < 0.5 and clickable:
            return Action(type="click", element=rng.choice(clickable).id)
        textboxes = [e for e in obs.elements if e.role == "textbox"]
        if roll < 0.7 and textboxes:
            return Action(type="type", element=rng.choice(textboxes).id, text=rng.choice(WORDS),
                          submit=rng.random() < 0.5)
        if roll < 0.8:
            return Action(type="press", key="Enter")
        if roll < 0.9:
            return Action(type="scroll", direction=rng.choice(["up", "down"]), amount=400)
        if roll < 0.95:
            return Action(type="back")
        return Action(type="click", x=float(rng.randint(0, 1200)), y=float(rng.randint(0, 780)))

    def stop(self) -> None:
        return None
