"""Command line: serve the shop, run agents, summarise results, build the viewer, run the demo."""

import argparse
import logging
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

from shopgym.config import SERVE_PORT, data_dir

DEMO_AGENTS = ["oracle", "noop", "random"]


def make_agent(name: str, seed: int, mode: str) -> Any:
    from shopgym.agents.baselines import NoOpAgent, RandomAgent
    from shopgym.agents.llm import LLMAgent, provider_from_env
    from shopgym.agents.oracle import OracleAgent
    from shopgym.agents.oracles import ALL_ORACLES

    if name == "oracle":
        return OracleAgent(ALL_ORACLES)
    if name == "noop":
        return NoOpAgent()
    if name == "random":
        return RandomAgent(seed)
    if name == "llm":
        return LLMAgent(provider_from_env(), mode=mode)
    raise SystemExit(f"unknown agent {name!r}")


def _serve(args: argparse.Namespace) -> None:
    import uvicorn

    uvicorn.run("shopgym.app.server:create_app", factory=True, host=args.host, port=args.port,
                log_level="warning")


def _start_server(port: int, log_path: Path) -> subprocess.Popen:
    env = {**os.environ, "SHOPGYM_DATA_DIR": str(data_dir())}
    log = open(log_path, "w")  # noqa: SIM115  (lives as long as the child process)
    proc = subprocess.Popen([sys.executable, "-m", "shopgym", "serve", "--port", str(port)],
                            env=env, stdout=log, stderr=subprocess.STDOUT)
    for _ in range(100):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1)
            return proc
        except OSError:
            time.sleep(0.2)
    proc.kill()
    raise SystemExit(f"server did not start, see {log_path}")


def _run(args: argparse.Namespace) -> None:
    from shopgym.harness.report import score_table, write_summary
    from shopgym.harness.runner import run_suite
    from shopgym.tasks.registry import load_tasks

    tasks = None if args.tasks == "all" else args.tasks.split(",")
    if tasks is not None:
        unknown = set(tasks) - set(load_tasks())
        if unknown:
            raise SystemExit(f"unknown tasks: {', '.join(sorted(unknown))}")
    if "llm" in args.agents.split(",") and os.environ.get("SHOPGYM_PROVIDER", "anthropic") == "anthropic" \
            and not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("the llm agent needs ANTHROPIC_API_KEY (or SHOPGYM_PROVIDER=openai); see .env.example")
    seeds = [int(s) for s in args.seeds.split(",")] if args.seeds else None
    run_dir = Path(args.run_dir).resolve()
    run_suite(args.agents.split(","), agent_factory=lambda a, s: make_agent(a, s, args.mode),
              base_url=args.base_url, data_dir=data_dir(), run_dir=run_dir, task_ids=tasks, seeds=seeds,
              workers=args.workers, resume=not args.force, headless=not args.headed)
    print(score_table(write_summary(run_dir)))


def _demo(args: argparse.Namespace) -> None:
    from shopgym.harness.report import score_table, write_summary
    from shopgym.harness.runner import run_suite
    from shopgym.harness.viewer import build_viewer

    run_dir = Path(args.run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    server = _start_server(SERVE_PORT, run_dir / "server.log")
    try:
        print(f"shop running at http://127.0.0.1:{SERVE_PORT}/ (headless, keyless)")
        run_suite(DEMO_AGENTS, agent_factory=lambda a, s: make_agent(a, s, "text"),
                  base_url=f"http://127.0.0.1:{SERVE_PORT}", data_dir=data_dir(), run_dir=run_dir,
                  workers=args.workers, resume=False, headless=True)
    finally:
        server.terminate()
        server.wait(timeout=10)
    summary = write_summary(run_dir)
    viewer = build_viewer(run_dir, run_dir / "viewer.html")
    print(score_table(summary))
    print(f"viewer: {viewer}")


def _check_run_dir(path: str) -> Path:
    run_dir = Path(path).resolve()
    if not (run_dir / "summary.json").exists() and not any(run_dir.glob("*/*/*/result.json")):
        raise SystemExit(f"no run results found in {run_dir}")
    return run_dir


def _report(args: argparse.Namespace) -> None:
    from shopgym.harness.report import score_table, write_summary

    print(score_table(write_summary(_check_run_dir(args.run_dir))))


def _view(args: argparse.Namespace) -> None:
    from shopgym.harness.viewer import build_viewer

    run_dir = _check_run_dir(args.run_dir)
    print(build_viewer(run_dir, Path(args.out).resolve()))


def _tasks(_: argparse.Namespace) -> None:
    from shopgym.tasks.registry import load_tasks

    for task in load_tasks().values():
        print(f"{task.tier:<7} {task.id:<28} {task.instruction}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="shopgym", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    serve = sub.add_parser("serve", help="run the storefront (default port 4200)")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=SERVE_PORT)
    serve.set_defaults(fn=_serve)

    run = sub.add_parser("run", help="run agents over tasks against a running server")
    run.add_argument("--agents", default="oracle", help="comma list: oracle,noop,random,llm")
    run.add_argument("--tasks", default="all", help="'all' or a comma list of task ids")
    run.add_argument("--seeds", default="", help="comma list of seeds (default: each task's seed)")
    run.add_argument("--mode", default="text", choices=["text", "screenshot"], help="llm observation mode")
    run.add_argument("--base-url", default=f"http://127.0.0.1:{SERVE_PORT}")
    run.add_argument("--run-dir", default="runs/manual")
    run.add_argument("--workers", type=int, default=4)
    run.add_argument("--force", action="store_true", help="ignore finished episodes on disk")
    run.add_argument("--headed", action="store_true")
    run.set_defaults(fn=_run)

    demo = sub.add_parser("demo", help="keyless demo: serve, run oracle+noop+random, print table, write viewer")
    demo.add_argument("--run-dir", default="runs/demo")
    demo.add_argument("--workers", type=int, default=4)
    demo.set_defaults(fn=_demo)

    report = sub.add_parser("report", help="print the score table for a run directory")
    report.add_argument("run_dir")
    report.set_defaults(fn=_report)

    view = sub.add_parser("view", help="write a self-contained HTML viewer for a run directory")
    view.add_argument("run_dir")
    view.add_argument("--out", default="viewer.html")
    view.set_defaults(fn=_view)

    tasks = sub.add_parser("tasks", help="list the tasks")
    tasks.set_defaults(fn=_tasks)
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    args = _parser().parse_args(argv)
    args.fn(args)
    return 0
