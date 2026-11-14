"""Summaries: score table per agent and tier, written as JSON and printed."""

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from shopgym.tasks.registry import TIERS


def load_results(run_dir: Path) -> list[dict[str, Any]]:
    return [json.loads(p.read_text()) for p in sorted(run_dir.glob("*/*/*/result.json"))]


def summarise(results: list[dict[str, Any]]) -> dict[str, Any]:
    by_agent: dict[str, list[dict]] = defaultdict(list)
    for r in results:
        by_agent[r["agent"]].append(r)
    summary = {}
    for agent, rows in sorted(by_agent.items()):
        tiers = {}
        for tier in TIERS:
            subset = [r for r in rows if r["tier"] == tier]
            if subset:
                tiers[tier] = {"passed": sum(r["success"] for r in subset), "total": len(subset)}
        summary[agent] = {
            "passed": sum(r["success"] for r in rows),
            "total": len(rows),
            "success_rate": round(sum(r["success"] for r in rows) / len(rows), 4) if rows else 0.0,
            "mean_steps": round(sum(r["steps"] for r in rows) / len(rows), 2) if rows else 0.0,
            "crashes": sum(1 for r in rows if r["crash"]),
            "tiers": tiers,
            "failures": sorted(r["task"] for r in rows if not r["success"]),
        }
    return summary


def score_table(summary: dict[str, Any]) -> str:
    header = f"{'agent':<10}{'easy':>10}{'medium':>10}{'hard':>10}{'overall':>12}{'steps':>8}{'crashes':>9}"
    lines = [header, "-" * len(header)]
    for agent, s in summary.items():
        cells = []
        for tier in TIERS:
            t = s["tiers"].get(tier)
            cells.append(f"{t['passed']}/{t['total']}" if t else "-")
        overall = f"{s['passed']}/{s['total']} {s['success_rate'] * 100:.0f}%"
        lines.append(f"{agent:<10}{cells[0]:>10}{cells[1]:>10}{cells[2]:>10}{overall:>12}"
                     f"{s['mean_steps']:>8.1f}{s['crashes']:>9}")
    return "\n".join(lines)


def write_summary(run_dir: Path) -> dict[str, Any]:
    summary = summarise(load_results(run_dir))
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    return summary
