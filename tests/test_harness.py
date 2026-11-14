"""Harness: a recorded run builds a summary table and a self-contained viewer; resume skips work."""

import json

import pytest

from shopgym.agents.baselines import NoOpAgent
from shopgym.cli import main
from shopgym.harness.report import score_table, summarise
from shopgym.harness.runner import run_suite
from shopgym.harness.viewer import build_viewer
from shopgym.tasks.registry import load_tasks

pytestmark = pytest.mark.e2e


def test_run_report_viewer_and_resume(live_server, tmp_path):
    run_dir = tmp_path / "run"
    factory = lambda name, seed: NoOpAgent()  # noqa: E731
    kwargs = dict(agent_factory=factory, base_url=live_server["base_url"], data_dir=live_server["data_dir"],
                  run_dir=run_dir, task_ids=["newsletter-subscribe", "search-count"], workers=2)
    results = run_suite(["noop"], **kwargs)
    assert len(results) == 2 and not any(r["success"] for r in results)

    summary = summarise(results)
    assert summary["noop"]["total"] == 2 and "noop" in score_table(summary)

    viewer = build_viewer(run_dir, tmp_path / "viewer.html")
    html = viewer.read_text()
    assert "search-count" in html and "http" not in html.split("<script>")[0].split("<body>")[0]

    # Resume: finished episodes are not run again.
    before = {p: p.stat().st_mtime for p in run_dir.glob("noop/*/*/result.json")}
    again = run_suite(["noop"], **kwargs)
    assert len(again) == 2
    assert {p: p.stat().st_mtime for p in run_dir.glob("noop/*/*/result.json")} == before


def test_cli_lists_tasks_and_rejects_unknown_ones(capsys):
    assert main(["tasks"]) == 0
    out = capsys.readouterr().out
    assert len(out.strip().splitlines()) == len(load_tasks())
    with pytest.raises(SystemExit):
        main(["run", "--tasks", "no-such-task", "--agents", "noop"])


def test_result_json_is_plain(live_server, tmp_path):
    run_dir = tmp_path / "plain"
    run_suite(["noop"], agent_factory=lambda n, s: NoOpAgent(), base_url=live_server["base_url"],
              data_dir=live_server["data_dir"], run_dir=run_dir, task_ids=["newsletter-subscribe"], workers=1)
    data = json.loads(next(run_dir.glob("noop/*/*/result.json")).read_text())
    assert set(data) >= {"agent", "task", "tier", "seed", "success", "reward", "steps", "verdict", "crash"}
