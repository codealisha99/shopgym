"""Self-contained HTML trajectory viewer. One file, no network: screenshots are embedded as JPEG data URIs."""

import base64
import io
import json
from pathlib import Path
from typing import Any

from PIL import Image

from shopgym.harness.report import load_results

THUMB_WIDTH = 760
TEMPLATE = Path(__file__).parent / "viewer_template.html"


def _thumb(path: Path) -> str:
    if not path.stat().st_size:  # a screenshot that stalled was recorded empty
        return ""
    image = Image.open(path).convert("RGB")
    height = round(image.height * THUMB_WIDTH / image.width)
    image = image.resize((THUMB_WIDTH, height))
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=62, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _episode(run_dir: Path, result: dict[str, Any]) -> dict[str, Any]:
    folder = run_dir / result["agent"] / result["task"] / str(result["seed"])
    traj = json.loads((folder / "trajectory.json").read_text())
    frames = []
    for step in traj["steps"]:
        frames.append({"url": step["before"]["url"], "text": step["before"]["text"],
                       "shot": _thumb(folder / step["before"]["screenshot"]), "error": step["before"]["last_error"],
                       "action": step["action"], "reward": step["reward"], "done": step["done"],
                       "result_error": step["error"], "verdict": step["info"].get("verdict")})
    final = traj["final"]
    frames.append({"url": final["url"], "text": final["text"], "shot": _thumb(folder / final["screenshot"]),
                   "error": final["last_error"], "action": None, "reward": None, "done": True,
                   "result_error": None, "verdict": None})
    return {"key": f"{result['agent']}/{result['task']}/{result['seed']}", "result": result, "frames": frames}


def build_viewer(run_dir: Path, out_file: Path) -> Path:
    results = load_results(run_dir)
    episodes = [_episode(run_dir, r) for r in sorted(results, key=lambda r: (r["agent"], r["task"], r["seed"]))]
    data = json.dumps(episodes).replace("</", "<\\/")
    html = TEMPLATE.read_text().replace("/*__DATA__*/null", data)
    out_file.write_text(html)
    return out_file
