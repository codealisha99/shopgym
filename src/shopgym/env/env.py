"""ShopGymEnv: a Gymnasium-style computer-use environment over the storefront.

    env = ShopGymEnv(base_url="http://127.0.0.1:4200", data_dir=Path("data"))
    obs = env.reset("newsletter-subscribe", seed=7)
    obs, reward, done, info = env.step({"type": "click", "element": "e4"})

reward is 1.0 only when the task checker passes. The checker runs when the agent calls `finish`
or when the step budget runs out (then with no answer).
"""

from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

from shopgym.env.actions import Action, ActionError, apply_action, parse_action, settle
from shopgym.env.episodes import Episode, create_episode, remove_episode
from shopgym.env.observe import Observation, capture
from shopgym.tasks.checkers import CheckContext
from shopgym.tasks.registry import Task, get_task

VIEWPORT = {"width": 1280, "height": 800}


@dataclass(frozen=True)
class StepResult:
    observation: Observation
    reward: float
    done: bool
    info: dict[str, Any]


class ShopGymEnv:
    def __init__(self, base_url: str, data_dir: Path, *, headless: bool = True,
                 keep_episodes: bool = False) -> None:
        self._base_url = base_url.rstrip("/")
        self._data_dir = Path(data_dir)
        self._headless = headless
        self._keep = keep_episodes
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._task: Task | None = None
        self._episode: Episode | None = None
        self._steps = 0
        self._done = True
        self._last_error: str | None = None

    @property
    def initial_db(self) -> Path:
        """Snapshot of the episode database right after setup. Oracles and checkers read this."""
        return self._episode.initial

    # -- lifecycle -------------------------------------------------------------------------
    def __enter__(self) -> "ShopGymEnv":
        return self

    def __exit__(self, *exc: tuple[type[BaseException], BaseException, TracebackType]) -> None:
        self.close()

    def close(self) -> None:
        self._end_episode()
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._pw is not None:
            self._pw.stop()
            self._pw = None

    def _end_episode(self) -> None:
        if self._context is not None:
            self._context.close()
            self._context = None
        if self._episode is not None and not self._keep:
            remove_episode(self._episode)
        self._episode = None

    def _ensure_browser(self) -> Browser:
        if self._browser is None:
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch(headless=self._headless)
        return self._browser

    # -- Gymnasium-style API ----------------------------------------------------------------
    def reset(self, task_id: str, seed: int | None = None) -> Observation:
        self._end_episode()
        self._task = get_task(task_id)
        seed = self._task.seed if seed is None else seed
        self._episode = create_episode(self._data_dir, seed, self._task.make_setup())
        self._context = self._ensure_browser().new_context(viewport=VIEWPORT)
        self._context.add_cookies([{"name": k, "value": v, "url": self._base_url}
                                   for k, v in self._episode.cookies.items()])
        self._page = self._context.new_page()
        self._page.goto(self._base_url + self._task.start_url, wait_until="load")
        self._steps, self._done, self._last_error = 0, False, None
        return self._observe()

    def step(self, action: Action | dict | str) -> StepResult:
        if self._task is None or self._done:
            raise RuntimeError("call reset() before step(), and do not step after the episode is done")
        self._steps += 1
        self._last_error = None
        try:
            parsed = action if isinstance(action, Action) else parse_action(action)
        except ActionError as exc:
            self._last_error = str(exc)
            return self._finish_or_continue()
        if parsed.type == "finish":
            return self._finish(parsed.answer)
        try:
            apply_action(self._page, parsed, self._base_url)
        except ActionError as exc:
            self._last_error = str(exc)
        except Exception as exc:  # Playwright timeouts and similar are the agent's problem, not a crash
            self._last_error = f"{type(exc).__name__}: {str(exc).splitlines()[0]}"
        return self._finish_or_continue()

    # -- internals ---------------------------------------------------------------------------
    def _observe(self) -> Observation:
        return capture(self._page, step=self._steps, steps_left=self._steps_left(),
                       instruction=self._task.instruction, last_error=self._last_error)

    def _steps_left(self) -> int:
        return max(0, self._task.max_steps - self._steps)

    def _finish_or_continue(self) -> StepResult:
        if self._steps < self._task.max_steps:
            return StepResult(self._observe(), 0.0, False,
                              {"steps": self._steps, "truncated": False, "verdict": None, "error": self._last_error})
        # Budget spent without finish: the checker still judges the state, with no answer.
        verdict = self._grade(answer=None)
        self._done = True
        return StepResult(self._observe(), float(verdict.ok), True,
                          {"steps": self._steps, "truncated": True, "verdict": verdict_dict(verdict),
                           "error": self._last_error})

    def _finish(self, answer: str | None) -> StepResult:
        verdict = self._grade(answer)
        self._done = True
        return StepResult(self._observe(), float(verdict.ok), True,
                          {"steps": self._steps, "truncated": False, "verdict": verdict_dict(verdict),
                           "error": self._last_error})

    def _grade(self, answer: str | None):
        # The server commits each request before responding, so the episode database is current here.
        settle(self._page)
        ctx = CheckContext(initial=self._episode.initial, final=self._episode.db, answer=answer)
        return self._task.evaluate(ctx)


def verdict_dict(verdict) -> dict[str, Any]:
    return {"ok": verdict.ok, "reason": verdict.reason}
