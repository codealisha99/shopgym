"""Build the landing-page replay from real oracle episodes in a `make demo` run.

Usage (from the repo root):  uv run python site/tools/build_replay.py runs/demo

Writes WebP frames to site/replay/ and replaces the block between the replay markers in
site/index.html. Frames are the real screenshots taken during the run, downscaled to 640 px wide.
Captions are the real actions (element label and value) and the checker verdict.
"""

import html
import json
import re
import sys
from pathlib import Path

from PIL import Image

EPISODES = [
    ("newsletter-subscribe", "Subscribe", "Easy: subscribe to the newsletter"),
    ("cancel-order-1042", "Cancel", "Medium: cancel one order, leave the others"),
    ("admin-refund-disambiguated", "Refund", "Hard: refund one of two customers with the same name"),
    ("guest-checkout", "Checkout", "Medium: guest checkout with a test card"),
]
WIDTH = 640
QUALITY = 55
SITE = Path(__file__).resolve().parents[1]
START, END = "<!-- replay:start -->", "<!-- replay:end -->"


def element_label(text: str, element: str | None) -> str:
    if not element:
        return ""
    match = re.search(rf"^\[{re.escape(element)}\] (.*)$", text, re.MULTILINE)
    return match.group(1).split(" -> ")[0] if match else element


def describe(action: dict, before_text: str) -> str:
    kind = action["type"]
    if kind == "finish":
        return f"finish, answer “{action.get('answer') or ''}”" if action.get("answer") else "finish"
    label = element_label(before_text, action.get("element"))
    if kind == "type":
        return f"type “{action['text']}” into {label}"
    if kind == "click":
        return f"click {label}"
    return f"{kind} {label}".strip()


def frame_file(run_dir: Path, slug: str, index: int, source: Path, out_dir: Path) -> str:
    image = Image.open(source).convert("RGB")
    height = round(image.height * WIDTH / image.width)
    name = f"{slug}-{index:02d}.webp"
    image.resize((WIDTH, height), Image.LANCZOS).save(out_dir / name, "WEBP", quality=QUALITY, method=6)
    return name


def episode_block(run_dir: Path, slug: str, title: str, out_dir: Path, active: bool) -> str:
    folder = run_dir / "oracle" / slug / "7"
    traj = json.loads((folder / "trajectory.json").read_text())
    result = traj["result"]
    steps = []
    for i, step in enumerate(traj["steps"]):
        before = step["before"]
        name = frame_file(run_dir, slug, i, folder / before["screenshot"], out_dir)
        steps.append((describe(step["action"], before["text"]), name))
    final_name = frame_file(run_dir, slug, len(steps), folder / traj["final"]["screenshot"], out_dir)
    steps.append(("end of episode: checker reads the database and the answer", final_name))
    verdict = "passed" if result["success"] else "failed"
    items = "\n".join(
        f'        <li><button type="button" data-frame="{n}" aria-controls="{slug}-view"'
        f' aria-current="{"true" if n == 0 else "false"}">'
        f'<span class="step-n">{n + 1}</span> {html.escape(caption)}</button></li>'
        for n, (caption, _) in enumerate(steps))
    first = steps[0][1]
    frames = "\n".join(
        f'      <img data-n="{n}" src="replay/{name}" width="{WIDTH}" height="{round(WIDTH * 0.625)}" '
        f'loading="lazy" alt="{html.escape("Step " + str(n + 1) + ": " + caption)}"{"" if n == 0 else " hidden"}>'
        for n, (caption, name) in enumerate(steps))
    return f"""    <section class="replay-episode" id="ep-{slug}" aria-label="{html.escape(title)}" {'' if active else 'hidden'}>
      <p class="replay-meta">{html.escape(title)}. Checker verdict: <strong>{verdict}</strong>
        in {result['steps']} actions. Seed 7, scripted oracle.</p>
      <div class="replay-grid">
        <ol class="replay-steps" aria-label="Actions">
{items}
        </ol>
        <figure class="replay-view" id="{slug}-view" aria-live="polite">
{frames}
        </figure>
      </div>
    </section>"""


def build(run_dir: Path) -> None:
    out_dir = SITE / "replay"
    out_dir.mkdir(exist_ok=True)
    for old in out_dir.glob("*.webp"):
        old.unlink()
    tabs, panels = [], []
    for i, (slug, short, title) in enumerate(EPISODES):
        tabs.append(f'<button type="button" role="tab" data-ep="{slug}" aria-selected="{str(i == 0).lower()}">'
                    f'{html.escape(short)}</button>')
        panels.append(episode_block(run_dir, slug, title, out_dir, active=i == 0))
    block = (f'{START}\n  <div class="replay" data-replay>\n    <div class="replay-tabs" role="tablist">'
             + "".join(tabs) + "</div>\n" + "\n".join(panels) + f"\n  </div>\n  {END}")
    index = SITE / "index.html"
    text = index.read_text()
    text = re.sub(re.escape(START) + r".*?" + re.escape(END), lambda _: block, text, flags=re.S)
    index.write_text(text)
    print(f"wrote {len(list(out_dir.glob('*.webp')))} frames, index updated")


if __name__ == "__main__":
    build(Path(sys.argv[1]).resolve())
