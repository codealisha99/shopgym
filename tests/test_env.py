"""Browser-level tests against the live server: determinism, errors, isolation, solvability, baselines."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from shopgym.agents.baselines import NoOpAgent
from shopgym.agents.oracle import OracleAgent
from shopgym.agents.oracles import ALL_ORACLES
from shopgym.env.actions import ActionError
from shopgym.env.env import ShopGymEnv
from shopgym.harness.runner import run_episode
from shopgym.tasks.registry import load_tasks

pytestmark = pytest.mark.e2e
TASKS = load_tasks()


@pytest.fixture()
def env(live_server):
    with ShopGymEnv(live_server["base_url"], live_server["data_dir"]) as e:
        yield e


def test_same_seed_gives_same_observation(env):
    first = env.reset("newsletter-subscribe", seed=7)
    second = env.reset("newsletter-subscribe", seed=7)
    assert first.text == second.text
    assert first.elements == second.elements
    assert first.screenshot == second.screenshot


def test_different_seed_changes_the_page(env):
    a = env.reset("search-count", seed=7)
    b = env.reset("search-count", seed=8)
    assert a.text != b.text


def test_bad_element_id_is_reported_not_raised(env):
    env.reset("newsletter-subscribe")
    result = env.step({"type": "click", "element": "e9999"})
    assert not result.done and "no element e9999" in result.observation.last_error


def test_invalid_action_is_reported_and_counts_as_a_step(env):
    env.reset("newsletter-subscribe")
    result = env.step("definitely not json")
    assert result.observation.last_error and result.observation.steps_left == TASKS["newsletter-subscribe"].max_steps - 1


def test_step_after_done_is_an_error(env):
    env.reset("newsletter-subscribe")
    env.step({"type": "finish", "answer": ""})
    with pytest.raises(RuntimeError):
        env.step({"type": "finish", "answer": ""})


def test_budget_exhaustion_ends_episode_and_grades_state(env):
    env.reset("newsletter-subscribe")
    result = None
    for _ in range(TASKS["newsletter-subscribe"].max_steps):
        result = env.step({"type": "press", "key": "Escape"})
    assert result.done and result.info["truncated"] and result.reward == 0.0


def test_navigation_outside_site_is_refused_by_the_action_parser():
    from shopgym.env.actions import parse_action

    with pytest.raises(ActionError):
        parse_action({"type": "goto", "url": "http://example.com"})


@pytest.mark.parametrize("task_id", sorted(TASKS))
def test_oracle_solves_every_task(live_server, tmp_path, task_id):
    task = TASKS[task_id]
    result = run_episode(OracleAgent(ALL_ORACLES), task, base_url=live_server["base_url"],
                         data_dir=live_server["data_dir"], out_dir=tmp_path / task_id, seed=task.seed)
    assert result["success"], f"{task_id}: {result['verdict']} crash={result['crash']}"


def test_noop_scores_zero_on_every_task(live_server, tmp_path):
    scores = [run_episode(NoOpAgent(), t, base_url=live_server["base_url"], data_dir=live_server["data_dir"],
                          out_dir=tmp_path / t.id, seed=t.seed)["success"] for t in TASKS.values()]
    assert not any(scores)


def test_parallel_episodes_are_isolated(live_server):
    """Four episodes run at once; each adds a different product through its own browser context."""
    skus = ["CLO-TRP-01", "CLO-TOT-02", "BOK-ATL-01", "HOM-LMP-02"]

    def episode(sku):
        with ShopGymEnv(live_server["base_url"], live_server["data_dir"], keep_episodes=True) as env:
            env.reset("newsletter-subscribe")
            env._page.request.post(live_server["base_url"] + "/cart/add", form={"sku": sku, "qty": "1"})
            return sku, env._episode.db

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(episode, skus))
    from shopgym.app.db import connect

    for sku, db in results:
        rows = connect(db).execute("SELECT p.sku FROM cart_items c JOIN products p ON p.id = c.product_id").fetchall()
        assert [r[0] for r in rows] == [sku]
