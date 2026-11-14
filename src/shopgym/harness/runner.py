"""Run agents over tasks. Records a trajectory per episode, resumes from disk, runs in parallel.

Output layout:
  <run_dir>/<agent>/<task>/<seed>/result.json       outcome (its presence marks the episode done)
  <run_dir>/<agent>/<task>/<seed>/trajectory.json   every observation, action and result
  <run_dir>/<agent>/<task>/<seed>/screens/*.png     screenshot per observation
"""

import json
import logging
import traceback
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from shopgym.env.env import ShopGymEnv
from shopgym.env.observe import Observation
from shopgym.tasks.registry import Task, load_tasks

log = logging.getLogger("shopgym.runner")
AgentFactory = Callable[[str, int], Any]


def _obs_record(obs: Observation, shots: Path, label: str) -> dict[str, Any]:
    shot_path = shots / f"{label}.png"
    shot_path.write_bytes(obs.screenshot)
    return {"url": obs.url, "title": obs.title, "text": obs.text, "screenshot": f"screens/{label}.png",
            "step": obs.step, "steps_left": obs.steps_left, "last_error": obs.last_error}


def _action_record(action: Any) -> Any:
    if is_dataclass(action):
        return {k: v for k, v in asdict(action).items() if v not in (None, False)}
    return action


def run_episode(agent: Any, task: Task, *, base_url: str, data_dir: Path, out_dir: Path, seed: int,
                headless: bool = True) -> dict[str, Any]:
    """One agent, one task, one seed. Always returns a result dict, even if the agent crashes."""
    shots = out_dir / "screens"
    shots.mkdir(parents=True, exist_ok=True)
    steps: list[dict[str, Any]] = []
    crash = None
    info: dict[str, Any] = {}
    reward = 0.0
    with ShopGymEnv(base_url, data_dir, headless=headless) as env:
        obs = env.reset(task.id, seed)
        try:
            agent.start(task, obs, env.initial_db)
            while True:
                action = agent.act(obs)
                label = f"{obs.step:03d}"
                before = _obs_record(obs, shots, label)
                result = env.step(action)
                steps.append({"before": before, "action": _action_record(action), "reward": result.reward,
                              "done": result.done, "info": result.info, "error": result.info.get("error")})
                obs, info, reward = result.observation, result.info, result.reward
                if result.done:
                    break
        except Exception as exc:  # an agent or oracle bug must not abort the whole suite
            crash = f"{type(exc).__name__}: {exc}"
            log.warning("episode crashed: %s", crash)
            log.debug("%s", traceback.format_exc())
            if not steps or not steps[-1]["done"]:
                steps.append({"before": _obs_record(obs, shots, f"{obs.step:03d}"), "action": None,
                              "reward": 0.0, "done": True, "info": {}, "error": crash})
        finally:
            if hasattr(agent, "stop"):
                agent.stop()
        final = _obs_record(obs, shots, "final")
    verdict = (info or {}).get("verdict") or {}
    result = {
        "agent": agent.name, "task": task.id, "tier": task.tier, "seed": seed,
        "success": bool(reward >= 1.0 and crash is None), "reward": reward,
        "steps": len(steps), "truncated": bool((info or {}).get("truncated")),
        "verdict": verdict, "crash": crash, "instruction": task.instruction,
    }
    (out_dir / "trajectory.json").write_text(json.dumps({"result": result, "steps": steps, "final": final},
                                                        indent=2))
    (out_dir / "result.json").write_text(json.dumps(result, indent=2))
    return result


def episode_dir(run_dir: Path, agent: str, task_id: str, seed: int) -> Path:
    return run_dir / agent / task_id / str(seed)


def run_suite(agents: list[str], *, agent_factory: AgentFactory, base_url: str, data_dir: Path, run_dir: Path,
              task_ids: list[str] | None = None, seeds: list[int] | None = None, workers: int = 4,
              resume: bool = True, headless: bool = True) -> list[dict[str, Any]]:
    tasks = load_tasks()
    selected = [tasks[t] for t in task_ids] if task_ids else list(tasks.values())
    jobs = []
    for agent in agents:
        for task in selected:
            for seed in seeds or [task.seed]:
                out = episode_dir(run_dir, agent, task.id, seed)
                if resume and (out / "result.json").exists():
                    continue
                jobs.append((agent, task, seed, out))
    results = [json.loads((episode_dir(run_dir, a, t.id, s) / "result.json").read_text())
               for a in agents for t in selected for s in (seeds or [t.seed])
               if (episode_dir(run_dir, a, t.id, s) / "result.json").exists() and resume]
    log.info("%d episodes to run, %d already done", len(jobs), len(results))

    def job(agent: str, task: Task, seed: int, out: Path) -> dict[str, Any]:
        return run_episode(agent_factory(agent, seed), task, base_url=base_url, data_dir=data_dir,
                           out_dir=out, seed=seed, headless=headless)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(job, *j) for j in jobs]
        for future in as_completed(futures):
            res = future.result()
            results.append(res)
            log.info("%-7s %-28s seed=%d success=%s steps=%d", res["agent"], res["task"], res["seed"],
                     res["success"], res["steps"])
    return results

