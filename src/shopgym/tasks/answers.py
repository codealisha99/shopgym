"""Tolerant matching for free-text answers.

Agents phrase answers in many ways ("3", "three", "3 reviews", "3 of 12", "$1,299.00", "Status: shipped",
"can't be cancelled"). Each matcher accepts those equivalent forms and rejects anything that could be
read as a different answer: two candidate numbers, a negated status ("not shipped"), or a name that is
only a prefix of a longer product name ("Desk Lamp" inside "Desk Lamp Pro").
"""

import re

_UNITS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
    "sixteen seventeen eighteen nineteen".split())}
_TENS = {w: 20 + 10 * i for i, w in enumerate("twenty thirty forty fifty sixty seventy eighty ninety".split())}
_UNIT_WORDS = "|".join(list(_UNITS)[1:10])
_TEN_WORDS = "|".join(_TENS)
_NUMBER = re.compile(
    r"(?<!\w)(\d+(?:,\d{3})*(?:\.\d+)?)(?!\w)"
    rf"|\b((?:{_TEN_WORDS})(?:[- ](?:{_UNIT_WORDS}))?|{'|'.join(_UNITS)})\b",
    re.IGNORECASE)
_SCALE = re.compile(r"\b(?:hundred|thousand|million|billion)\b", re.IGNORECASE)
_NEGATION = re.compile(r"\b(?:not|no|never|none|cannot|nothing)\b|n['’]t\b", re.IGNORECASE)
_OF_TOTAL = re.compile(r"^\s*(\d+)\s+(?:of|out of)\s+(?:the\s+)?\d+\b", re.IGNORECASE)
_REFUSAL = re.compile(
    r"\b(?:not|cannot|can['’]?t|can\s+not|unable\s+to|never)\s+(?:be\s+)?cancel|\bnon-?cancel", re.IGNORECASE)


def _numbers(text: str) -> list[float]:
    """Every number in the text, digits or number words, in order of appearance.

    Scale words ("three hundred") make the reading ambiguous, so they yield no numbers at all.
    """
    if _SCALE.search(text):
        return []
    values = []
    for m in _NUMBER.finditer(text):
        if m.group(1) is not None:
            values.append(float(m.group(1).replace(",", "")))
            continue
        words = re.split(r"[- ]", m.group(2).lower())
        values.append(float(sum(_UNITS.get(w, _TENS.get(w, 0)) for w in words)))
    return values


def count_answer(answer: str | None) -> int | None:
    """The single whole number the answer gives, or None. Accepts '3 of 12' as 3 (3 is the answer)."""
    if not answer or _NEGATION.search(answer):
        return None
    leading = _OF_TOTAL.match(answer)
    if leading:
        return int(leading.group(1))
    values = _numbers(answer)
    if len(values) != 1 or values[0] != int(values[0]):
        return None
    return int(values[0])


def money_answer(answer: str | None) -> float | None:
    """The single amount in dollars the answer gives, or None ('$1,299.00', '12.5', 'USD 12.50')."""
    if not answer or _NEGATION.search(answer):
        return None
    values = _numbers(answer)
    return values[0] if len(values) == 1 else None


def status_matches(answer: str | None, expected: str, vocabulary: set[str]) -> bool:
    """True when the answer names the expected order status and no other status word.

    Accepts 'shipped', 'Status: shipped.', 'The order is shipped'. Rejects 'not shipped' and
    'shipped, then delivered'. 'canceled' is treated as 'cancelled'.
    """
    if not answer or _NEGATION.search(answer):
        return False
    words = [_spelling(w) for w in re.findall(r"[a-z]+", answer.lower())]
    found = {w for w in words if w in {_spelling(v) for v in vocabulary}}
    return found == {_spelling(expected)}


def _spelling(word: str) -> str:
    return "cancelled" if word == "canceled" else word


def refusal_given(answer: str | None) -> bool:
    """True when the answer says the order cannot be cancelled ("not cancellable", "can't be cancelled")."""
    return bool(answer) and _REFUSAL.search(answer) is not None


def sku_given(answer: str | None, sku: str) -> bool:
    """True when the only SKU-shaped token in the answer is the expected SKU (case-insensitive)."""
    tokens = {t.upper() for t in re.findall(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+", answer or "")}
    return tokens == {sku.upper()}


def _normal(text: str) -> str:
    return " " + " ".join(re.findall(r"[a-z0-9]+", text.lower())) + " "


def product_name_given(answer: str | None, expected: set[str], all_names: list[str]) -> bool:
    """True when the answer names exactly one product, and it is one of the expected names.

    A name counts only if it is not inside a longer product name that the answer also mentions.
    """
    if not answer:
        return False
    text = _normal(answer)
    found = [n for n in all_names if _normal(n) in text]
    longest = [n for n in found if not any(n != m and _normal(n) in _normal(m) for m in found)]
    return len(longest) == 1 and longest[0] in expected
