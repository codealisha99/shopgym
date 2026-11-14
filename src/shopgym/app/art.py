"""Generated product illustrations: one flat SVG drawing per product type, deterministic from the name.

A product's type comes from keywords in its name ("Trail Runner" is a shoe, "Field Notes Atlas" is a book).
Its colour comes from a hash of the name, picked from one shared palette family, so the same product always
looks the same and the whole catalogue reads as one illustration set. Drawings use a 120 x 120 viewBox,
two tones, one accent and a dark ink, with a soft ground shadow. Book covers print the product title.
"""

import html
import zlib
from collections.abc import Callable
from dataclasses import dataclass

from markupsafe import Markup


@dataclass(frozen=True)
class Palette:
    bg: str
    main: str
    shade: str
    accent: str
    ink: str = "#1f2a26"


PALETTES = (
    Palette(bg="#efe5d1", main="#c4824a", shade="#9c6232", accent="#f8f2e6"),  # sand
    Palette(bg="#dce7d6", main="#5b8a69", shade="#41684e", accent="#f3f0e4"),  # sage
    Palette(bg="#dce2ea", main="#4d6a88", shade="#37506b", accent="#eef2f6"),  # slate
    Palette(bg="#f1dacd", main="#b5573a", shade="#8c3f28", accent="#f8ece6"),  # clay
    Palette(bg="#f2e6b9", main="#cf9f35", shade="#a7791f", accent="#fbf6e2"),  # ochre
    Palette(bg="#d1e6e2", main="#2e7c77", shade="#215f5b", accent="#eaf6f4"),  # teal
)

# Keyword -> drawing. First match wins, so the more specific phrases come first.
KEYWORDS: tuple[tuple[str, str], ...] = (
    ("trail runner", "shoe"), ("boot", "shoe"), ("shoe", "shoe"),
    ("tote", "tote"), ("bag", "tote"),
    ("bulb planter", "shears"), ("shears", "shears"),
    ("pour-over", "carafe"), ("carafe", "carafe"), ("mug", "mug"),
    ("lamp", "lamp"), ("hose", "hose"), ("watering can", "can"),
    ("field notes", "book"), ("atlas", "book"), ("field guide", "book"), ("almanac", "book"),
    ("cookbook", "book"), ("journal", "book"), ("sketchbook", "book"), ("map set", "book"),
    ("earbuds", "earbuds"), ("webcam", "lens"), ("camera", "lens"), ("speaker", "grille"),
    ("hub", "ports"), ("power bank", "ports"), ("plug", "ports"), ("keyboard", "keys"),
    ("skillet", "pan"), ("throw", "textile"), ("rug", "textile"), ("board", "board"), ("bookend", "board"),
    ("planter", "planter"), ("herb", "planter"), ("pad", "pad"), ("compost", "bin"),
    ("train", "train"), ("puzzle", "blocks"), ("blocks", "blocks"), ("tiles", "blocks"),
    ("kite", "kite"), ("chess", "chess"), ("fox", "plush"),
    ("shell", "jacket"), ("jacket", "jacket"), ("shirt", "garment"), ("vest", "garment"),
    ("fleece", "garment"), ("apron", "apron"), ("socks", "socks"), ("beanie", "beanie"),
)


def _shadow(p: Palette) -> str:
    return f'<ellipse cx="60" cy="106" rx="34" ry="5" fill="{p.ink}" opacity="0.12"/>'


def _shoe(p: Palette, _: str) -> str:
    return (f'<path d="M22 82 V56 Q22 46 32 46 L48 50 Q56 52 60 60 L70 68 Q88 70 100 74 Q104 78 100 82 Z" fill="{p.main}"/>'
            f'<path d="M22 82 H100 Q104 82 100 86 H22 Z" fill="{p.ink}"/>'
            f'<path d="M22 70 H58 Q60 76 52 78 H22 Z" fill="{p.shade}"/>'
            f'<circle cx="46" cy="58" r="2.2" fill="{p.accent}"/><circle cx="54" cy="62" r="2.2" fill="{p.accent}"/>'
            f'<circle cx="62" cy="66" r="2.2" fill="{p.accent}"/>')


def _tote(p: Palette, _: str) -> str:
    return (f'<path d="M40 50 Q40 26 60 26 Q80 26 80 50" fill="none" stroke="{p.ink}" stroke-width="4"/>'
            f'<rect x="28" y="46" width="64" height="54" rx="4" fill="{p.main}"/>'
            f'<rect x="28" y="46" width="64" height="12" rx="3" fill="{p.shade}"/>'
            f'<circle cx="60" cy="76" r="8" fill="{p.accent}"/><circle cx="60" cy="76" r="3" fill="{p.ink}"/>')


def _garment(p: Palette, _: str) -> str:
    return (f'<path d="M38 26 L48 22 Q60 34 72 22 L82 26 L100 44 L90 54 L84 48 L84 96 L36 96 L36 48 L30 54 L20 44 Z" fill="{p.main}"/>'
            f'<path d="M48 22 Q60 34 72 22 L68 30 Q60 38 52 30 Z" fill="{p.accent}"/>'
            f'<rect x="36" y="78" width="48" height="5" fill="{p.shade}"/>'
            f'<line x1="60" y1="40" x2="60" y2="96" stroke="{p.shade}" stroke-width="2"/>')


def _jacket(p: Palette, _: str) -> str:
    return (f'<path d="M40 24 L50 20 L60 30 L70 20 L80 24 L98 46 L88 56 L84 50 L84 98 L36 98 L36 50 L32 56 L22 46 Z" fill="{p.main}"/>'
            f'<line x1="60" y1="30" x2="60" y2="98" stroke="{p.ink}" stroke-width="2" stroke-dasharray="3 3"/>'
            f'<path d="M50 20 L60 30 L70 20 L66 40 L54 40 Z" fill="{p.shade}"/>'
            f'<rect x="36" y="74" width="48" height="4" fill="{p.shade}"/>'
            f'<rect x="36" y="86" width="48" height="4" fill="{p.shade}"/>')


def _apron(p: Palette, _: str) -> str:
    return (f'<path d="M48 22 Q60 30 72 22" fill="none" stroke="{p.ink}" stroke-width="3"/>'
            f'<path d="M40 24 L80 24 L84 54 L36 54 Z" fill="{p.accent}" stroke="{p.shade}" stroke-width="2"/>'
            f'<path d="M36 54 H84 L90 100 H30 Z" fill="{p.main}"/>'
            f'<line x1="30" y1="54" x2="84" y2="54" stroke="{p.ink}" stroke-width="2"/>'
            f'<rect x="46" y="66" width="28" height="14" rx="2" fill="{p.shade}"/>')


def _socks(p: Palette, _: str) -> str:
    return (f'<path d="M44 22 H72 V66 Q72 74 84 78 Q96 82 96 92 Q96 100 84 100 H44 Q38 100 38 92 V30 Q38 22 44 22 Z" fill="{p.main}"/>'
            f'<rect x="38" y="22" width="34" height="12" fill="{p.shade}"/>'
            f'<rect x="38" y="44" width="34" height="5" fill="{p.accent}"/>'
            f'<rect x="38" y="60" width="34" height="5" fill="{p.accent}"/>')


def _beanie(p: Palette, _: str) -> str:
    return (f'<path d="M28 80 Q28 22 60 22 Q92 22 92 80 Z" fill="{p.main}"/>'
            f'<rect x="26" y="74" width="68" height="18" rx="6" fill="{p.shade}"/>'
            f'<line x1="44" y1="30" x2="44" y2="70" stroke="{p.accent}" stroke-width="3" opacity="0.6"/>'
            f'<line x1="60" y1="24" x2="60" y2="70" stroke="{p.accent}" stroke-width="3" opacity="0.6"/>'
            f'<line x1="76" y1="30" x2="76" y2="70" stroke="{p.accent}" stroke-width="3" opacity="0.6"/>')


def _carafe(p: Palette, _: str) -> str:
    return (f'<rect x="38" y="62" width="44" height="36" rx="10" fill="{p.accent}" stroke="{p.shade}" stroke-width="2"/>'
            f'<rect x="42" y="74" width="36" height="22" rx="6" fill="{p.shade}" opacity="0.35"/>'
            f'<path d="M34 30 H86 L72 58 H48 Z" fill="{p.main}"/>'
            f'<rect x="34" y="26" width="52" height="7" rx="3" fill="{p.shade}"/>')


def _mug(p: Palette, _: str) -> str:
    return (f'<path d="M80 52 Q96 52 96 68 Q96 84 80 84" fill="none" stroke="{p.main}" stroke-width="7"/>'
            f'<rect x="28" y="40" width="54" height="54" rx="8" fill="{p.main}"/>'
            f'<ellipse cx="55" cy="40" rx="27" ry="5" fill="{p.shade}"/>'
            f'<rect x="28" y="70" width="54" height="8" fill="{p.accent}"/>')


def _lamp(p: Palette, _: str) -> str:
    return (f'<circle cx="60" cy="46" r="26" fill="{p.accent}" opacity="0.6"/>'
            f'<path d="M36 46 L44 22 H76 L84 46 Z" fill="{p.main}"/>'
            f'<rect x="36" y="44" width="48" height="5" fill="{p.shade}"/>'
            f'<line x1="60" y1="49" x2="60" y2="88" stroke="{p.ink}" stroke-width="3"/>'
            f'<ellipse cx="60" cy="92" rx="18" ry="5" fill="{p.shade}"/>')


def _hose(p: Palette, _: str) -> str:
    return (f'<ellipse cx="58" cy="64" rx="34" ry="24" fill="none" stroke="{p.main}" stroke-width="10"/>'
            f'<ellipse cx="58" cy="64" rx="18" ry="11" fill="none" stroke="{p.shade}" stroke-width="8"/>'
            f'<path d="M92 64 Q104 64 104 76 V84" fill="none" stroke="{p.ink}" stroke-width="6" stroke-linecap="round"/>'
            f'<rect x="98" y="84" width="14" height="10" rx="2" fill="{p.accent}"/>')


def _book(p: Palette, name: str) -> str:
    lines = _wrap(name, 9)[:4]
    title = "".join(f'<text x="43" y="{46 + i * 10}" font-family="Georgia, serif" font-size="7.6" font-weight="700" '
                    f'fill="{p.accent}">{html.escape(line)}</text>' for i, line in enumerate(lines))
    return (f'<rect x="30" y="20" width="62" height="78" rx="3" fill="{p.main}"/>'
            f'<rect x="30" y="20" width="9" height="78" fill="{p.shade}"/>'
            f'<rect x="41" y="86" width="50" height="2" fill="{p.accent}" opacity="0.5"/>'
            f'<rect x="41" y="28" width="46" height="2" fill="{p.accent}" opacity="0.5"/>{title}')


def _earbuds(p: Palette, _: str) -> str:
    return (f'<rect x="34" y="62" width="52" height="34" rx="14" fill="{p.main}"/>'
            f'<rect x="34" y="62" width="52" height="10" rx="5" fill="{p.shade}"/>'
            f'<rect x="36" y="84" width="48" height="3" rx="1.5" fill="{p.accent}" opacity="0.6"/>'
            f'<rect x="34" y="28" width="12" height="40" rx="6" fill="{p.accent}" stroke="{p.shade}" stroke-width="2"/>'
            f'<rect x="74" y="28" width="12" height="40" rx="6" fill="{p.accent}" stroke="{p.shade}" stroke-width="2"/>')


def _lens(p: Palette, _: str) -> str:
    return (f'<rect x="28" y="36" width="64" height="44" rx="10" fill="{p.main}"/>'
            f'<circle cx="60" cy="58" r="15" fill="{p.shade}"/><circle cx="60" cy="58" r="8" fill="{p.ink}"/>'
            f'<circle cx="56" cy="54" r="2.5" fill="{p.accent}"/>'
            f'<rect x="50" y="80" width="20" height="8" fill="{p.shade}"/>')


def _grille(p: Palette, _: str) -> str:
    dots = "".join(f'<circle cx="{x}" cy="{y}" r="2.6" fill="{p.shade}"/>'
                   for x in range(42, 80, 9) for y in range(44, 92, 9))
    return (f'<rect x="32" y="30" width="56" height="70" rx="12" fill="{p.main}"/>{dots}'
            )


def _ports(p: Palette, _: str) -> str:
    ports = "".join(f'<rect x="{x}" y="58" width="8" height="12" rx="1.5" fill="{p.ink}"/>' for x in (38, 50, 62, 74))
    return (f'<rect x="28" y="44" width="64" height="36" rx="8" fill="{p.main}"/>'
            f'<rect x="28" y="44" width="64" height="8" rx="4" fill="{p.shade}"/>{ports}')


def _keys(p: Palette, _: str) -> str:
    keys = "".join(f'<rect x="{30 + c * 11}" y="{46 + r * 11}" width="8" height="8" rx="1.5" fill="{p.accent}"/>'
                   for r in range(3) for c in range(5))
    return f'<rect x="22" y="40" width="76" height="46" rx="8" fill="{p.main}"/>{keys}'


def _pan(p: Palette, _: str) -> str:
    return (f'<rect x="88" y="64" width="22" height="9" rx="4" fill="{p.ink}"/>'
            f'<ellipse cx="54" cy="66" rx="38" ry="16" fill="{p.ink}"/>'
            f'<ellipse cx="54" cy="62" rx="34" ry="13" fill="{p.main}"/>'
            f'<ellipse cx="54" cy="60" rx="22" ry="7" fill="{p.shade}" opacity="0.5"/>')


def _textile(p: Palette, _: str) -> str:
    bands = "".join(f'<rect x="26" y="{y}" width="68" height="6" fill="{p.accent}" opacity="0.7"/>' for y in (40, 56, 72, 88))
    return (f'<rect x="26" y="34" width="68" height="62" fill="{p.main}"/>{bands}'
            f'<rect x="22" y="94" width="76" height="6" fill="{p.ink}" opacity="0.25"/>')


def _board(p: Palette, _: str) -> str:
    grain = "".join(f'<line x1="26" y1="{y}" x2="94" y2="{y}" stroke="{p.shade}" stroke-width="1.5" opacity="0.6"/>'
                    for y in range(44, 96, 9))
    return (f'<rect x="20" y="36" width="80" height="50" rx="10" fill="{p.main}"/>{grain}'
            f'<circle cx="82" cy="50" r="4" fill="{p.accent}"/>')


def _shears(p: Palette, _: str) -> str:
    return (f'<line x1="44" y1="30" x2="82" y2="92" stroke="{p.main}" stroke-width="6" stroke-linecap="round"/>'
            f'<line x1="76" y1="30" x2="38" y2="92" stroke="{p.shade}" stroke-width="6" stroke-linecap="round"/>'
            f'<circle cx="38" cy="36" r="11" fill="none" stroke="{p.ink}" stroke-width="5"/>'
            f'<circle cx="82" cy="36" r="11" fill="none" stroke="{p.ink}" stroke-width="5"/>')


def _planter(p: Palette, _: str) -> str:
    return (f'<path d="M60 58 Q38 50 36 30 Q56 32 60 58 Z" fill="{p.main}"/>'
            f'<path d="M60 58 Q82 44 88 26 Q66 30 60 58 Z" fill="{p.shade}"/>'
            f'<path d="M34 60 H86 L78 98 H42 Z" fill="{p.accent}" stroke="{p.shade}" stroke-width="2"/>'
            f'<rect x="32" y="56" width="56" height="8" rx="3" fill="{p.main}"/>')


def _can(p: Palette, _: str) -> str:
    return (f'<path d="M92 40 L108 26" stroke="{p.ink}" stroke-width="5" stroke-linecap="round"/>'
            f'<path d="M46 44 Q60 14 78 44" fill="none" stroke="{p.ink}" stroke-width="5"/>'
            f'<path d="M30 44 H84 L78 98 H36 Z" fill="{p.main}"/>'
            f'<rect x="30" y="44" width="54" height="8" fill="{p.shade}"/>')


def _bin(p: Palette, _: str) -> str:
    return (f'<rect x="34" y="40" width="52" height="58" rx="4" fill="{p.main}"/>'
            f'<ellipse cx="60" cy="40" rx="30" ry="8" fill="{p.shade}"/>'
            f'<line x1="44" y1="60" x2="44" y2="90" stroke="{p.shade}" stroke-width="3"/>'
            f'<line x1="60" y1="60" x2="60" y2="90" stroke="{p.shade}" stroke-width="3"/>'
            f'<line x1="76" y1="60" x2="76" y2="90" stroke="{p.shade}" stroke-width="3"/>')


def _pad(p: Palette, _: str) -> str:
    return (f'<rect x="22" y="56" width="76" height="36" rx="14" fill="{p.main}"/>'
            f'<rect x="30" y="64" width="60" height="20" rx="8" fill="none" stroke="{p.accent}" stroke-width="2" stroke-dasharray="4 3"/>')


def _train(p: Palette, _: str) -> str:
    return (f'<rect x="26" y="58" width="50" height="26" rx="4" fill="{p.main}"/>'
            f'<rect x="60" y="44" width="28" height="40" rx="4" fill="{p.shade}"/>'
            f'<rect x="66" y="50" width="16" height="10" fill="{p.accent}"/>'
            f'<circle cx="38" cy="90" r="8" fill="{p.ink}"/><circle cx="74" cy="90" r="8" fill="{p.ink}"/>'
            f'<rect x="36" y="38" width="10" height="20" fill="{p.accent}"/>')


def _blocks(p: Palette, _: str) -> str:
    return (f'<rect x="24" y="60" width="34" height="34" rx="3" fill="{p.main}"/>'
            f'<rect x="62" y="60" width="34" height="34" rx="3" fill="{p.shade}"/>'
            f'<rect x="43" y="30" width="34" height="30" rx="3" fill="{p.accent}" stroke="{p.main}" stroke-width="2"/>')


def _kite(p: Palette, _: str) -> str:
    return (f'<path d="M60 22 L92 56 L60 94 L28 56 Z" fill="{p.main}"/>'
            f'<path d="M60 22 L92 56 L60 56 Z" fill="{p.shade}"/>'
            f'<line x1="60" y1="22" x2="60" y2="94" stroke="{p.ink}" stroke-width="1.5"/>'
            f'<path d="M60 94 Q52 102 60 106 Q68 110 60 114" fill="none" stroke="{p.ink}" stroke-width="2"/>')


def _chess(p: Palette, _: str) -> str:
    return (f'<circle cx="60" cy="38" r="13" fill="{p.main}"/>'
            f'<path d="M48 54 Q60 46 72 54 L80 90 H40 Z" fill="{p.main}"/>'
            f'<rect x="34" y="88" width="52" height="8" rx="2" fill="{p.shade}"/>'
            f'<rect x="38" y="96" width="44" height="6" rx="2" fill="{p.ink}"/>'
            f'<rect x="56" y="34" width="8" height="2" fill="{p.accent}"/>')


def _plush(p: Palette, _: str) -> str:
    return (f'<ellipse cx="66" cy="78" rx="26" ry="10" fill="{p.shade}"/>'
            f'<ellipse cx="58" cy="66" rx="30" ry="26" fill="{p.main}"/>'
            f'<path d="M36 52 L34 26 L52 42 Z" fill="{p.main}"/>'
            f'<path d="M80 52 L86 26 L68 42 Z" fill="{p.main}"/>'
            f'<ellipse cx="58" cy="76" rx="14" ry="10" fill="{p.accent}"/>'
            f'<circle cx="48" cy="62" r="3" fill="{p.ink}"/><circle cx="68" cy="62" r="3" fill="{p.ink}"/>'
            f'<circle cx="58" cy="72" r="2.5" fill="{p.ink}"/>')


def _generic(p: Palette, _: str) -> str:
    return (f'<rect x="30" y="34" width="60" height="60" rx="12" fill="{p.main}"/>'
            f'<rect x="30" y="34" width="60" height="16" rx="8" fill="{p.shade}"/>'
            f'<circle cx="60" cy="68" r="10" fill="{p.accent}"/>')


DRAWINGS: dict[str, Callable[[Palette, str], str]] = {
    "shoe": _shoe, "tote": _tote, "garment": _garment, "jacket": _jacket, "apron": _apron,
    "socks": _socks, "beanie": _beanie, "carafe": _carafe, "mug": _mug, "lamp": _lamp,
    "hose": _hose, "book": _book, "earbuds": _earbuds, "lens": _lens, "grille": _grille, "ports": _ports,
    "keys": _keys, "pan": _pan, "textile": _textile, "board": _board, "shears": _shears, "planter": _planter,
    "can": _can, "bin": _bin, "pad": _pad, "train": _train, "blocks": _blocks, "kite": _kite, "chess": _chess,
    "plush": _plush, "generic": _generic,
}


def drawing_for(name: str) -> str:
    lowered = name.lower()
    return next((kind for word, kind in KEYWORDS if word in lowered), "generic")


def _wrap(text: str, width: int) -> list[str]:
    lines, current = [], ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if len(candidate) > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    return lines + ([current] if current else [])


def product_art(name: str) -> Markup:
    """Inline SVG for a product, deterministic from its name. Safe to place in a template as-is."""
    palette = PALETTES[zlib.crc32(name.encode("utf-8")) % len(PALETTES)]
    body = DRAWINGS[drawing_for(name)](palette, name)
    svg = (f'<svg viewBox="0 0 120 120" focusable="false" style="background:{palette.bg}">'
           f'{_shadow(palette)}{body}</svg>')
    return Markup(svg)
