"""Build the landing-page replay from real oracle episodes in a `make demo` run.

Usage (from the repo root):  uv run python site/tools/build_replay.py runs/demo

Writes WebP frames to site/replay/ and replaces the block between the replay markers in
site/index.html. Frames are the real screenshots taken during the run, downscaled to 640 px wide.
Captions are the real actions (element label and value), the element each action acted on is
outlined using the box recorded in trajectory.json, and the last frame carries the checker verdict.
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
END_LABEL = "end of episode: checker reads the database and the answer"


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


def frame_file(slug: str, index: int, source: Path, out_dir: Path) -> tuple[str, tuple[int, int]]:
    image = Image.open(source).convert("RGB")
    height = round(image.height * WIDTH / image.width)
    name = f"{slug}-{index:02d}.webp"
    image.resize((WIDTH, height), Image.LANCZOS).save(out_dir / name, "WEBP", quality=QUALITY, method=6)
    return name, image.size


def target_style(box: list[int] | None, size: tuple[int, int]) -> str | None:
    """Percentages of the screenshot, so the outline scales with the image. None if the element was off-view."""
    if not box or box[2] <= 0 or box[3] <= 0:
        return None
    width, height = size
    x, y, w, h = box
    if x >= width or y >= height or x + w <= 0 or y + h <= 0:
        return None
    return (f"left:{100 * x / width:.2f}%;top:{100 * y / height:.2f}%;"
            f"width:{100 * w / width:.2f}%;height:{100 * h / height:.2f}%")


def episode_block(run_dir: Path, slug: str, title: str, out_dir: Path, active: bool) -> str:
    folder = run_dir / "oracle" / slug / "7"
    traj = json.loads((folder / "trajectory.json").read_text())
    result = traj["result"]
    steps = []  # (caption, frame name, target style or None)
    for i, step in enumerate(traj["steps"]):
        before = step["before"]
        name, size = frame_file(slug, i, folder / before["screenshot"], out_dir)
        caption = describe(step["action"], before["text"])
        style = target_style(step.get("target"), size)
        if step.get("target") and style is None:
            caption += " (the element is below this view)"
        steps.append((caption, name, style))
    final_name, _ = frame_file(slug, len(steps), folder / traj["final"]["screenshot"], out_dir)
    steps.append((END_LABEL, final_name, None))
    total = len(steps)
    verdict = result.get("verdict") or {}
    outcome = "passed" if result["success"] else "failed"
    reason = verdict.get("reason", "")
    chips = "".join(
        f'<button type="button" data-frame="{n}" aria-controls="{slug}-view" aria-current="{str(n == 0).lower()}"'
        f' aria-label="Step {n + 1}: {html.escape(caption, quote=True)}" title="{html.escape(caption, quote=True)}">'
        f'{n + 1}</button>'
        for n, (caption, _, _) in enumerate(steps))
    frames = "".join(
        f'<img data-n="{n}" src="replay/{name}" width="{WIDTH}" height="{round(WIDTH * 0.625)}" loading="lazy"'
        f' alt="{html.escape("Step " + str(n + 1) + ": " + caption, quote=True)}"{"" if n == 0 else " hidden"}>'
        for n, (caption, name, _) in enumerate(steps))
    outlines = "".join(
        f'<span class="target" data-n="{n}" style="{style}" hidden></span>'
        for n, (_, _, style) in enumerate(steps) if style)
    captions = "".join(
        f'<span class="caption-text" data-n="{n}"{"" if n == 0 else " hidden"}>{html.escape(caption)}</span>'
        for n, (caption, _, _) in enumerate(steps))
    return f"""    <section class="player-episode" id="ep-{slug}" aria-label="{html.escape(title)}" data-total="{total}"{'' if active else ' hidden'}>
      <p class="episode-title">{html.escape(title)}</p>
      <figure class="replay-view" id="{slug}-view" aria-live="off">
        <div class="frame">
          {frames}
          {outlines}
        </div>
        <figcaption class="replay-caption">
          <span class="step-count">Step 1 of {total}</span>
          <span class="caption-wrap">{captions}</span>
          <span class="verdict" data-outcome="{outcome}" hidden>Checker verdict: <strong>{outcome}</strong>. {html.escape(reason)}</span>
        </figcaption>
      </figure>
      <div class="replay-controls">
        <button type="button" data-act="restart" aria-label="Restart episode">Restart</button>
        <button type="button" data-act="prev" aria-label="Previous step">Prev</button>
        <button type="button" data-act="play" aria-pressed="false" aria-label="Play">Play</button>
        <button type="button" data-act="next" aria-label="Next step">Next</button>
        <input type="range" min="0" max="{total - 1}" value="0" step="1" aria-label="Scrub through the steps" data-scrub>
      </div>
      <nav class="replay-steps" aria-label="Steps of {html.escape(title)}">{chips}</nav>
      <p class="replay-meta">{result['steps']} actions, seed 7, scripted oracle, checker {outcome}.</p>
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
    block = (f'{START}\n      <div class="replay" data-replay>\n        <div class="replay-tabs" role="tablist">'
             + "".join(tabs) + "</div>\n" + "\n".join(panels) + f"\n      </div>\n    {END}")
    index = SITE / "index.html"
    text = index.read_text()
    text = re.sub(re.escape(START) + r".*?" + re.escape(END), lambda _: block, text, flags=re.S)
    index.write_text(text)
    print(f"wrote {len(list(out_dir.glob('*.webp')))} frames, index updated")


if __name__ == "__main__":
    build(Path(sys.argv[1]).resolve())
