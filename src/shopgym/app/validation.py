"""Form validation for customer input. Returns a dict of field -> message; empty dict means valid."""

import re
from datetime import date

POSTCODE_RE = re.compile(r"^[A-Za-z0-9 ]{4,10}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
COUNTRIES = ["United Kingdom", "Ireland", "France", "Germany", "Netherlands"]


def _blank(form, *names) -> dict:
    return {n: "Required." for n in names if not str(form.get(n, "")).strip()}


def validate_address(form) -> dict:
    errors = _blank(form, "full_name", "line1", "city", "postcode", "country")
    if "postcode" not in errors and not POSTCODE_RE.match(form["postcode"].strip()):
        errors["postcode"] = "Enter a postcode of 4 to 10 letters or digits."
    if form.get("country") not in COUNTRIES:
        errors["country"] = "Choose a country from the list."
    return errors


def validate_email(email: str) -> str | None:
    if not EMAIL_RE.match(email.strip()):
        return "Enter a valid email address."
    return None


def luhn_ok(number: str) -> bool:
    total, double = 0, False
    for ch in reversed(number):
        digit = int(ch)
        if double:
            digit = digit * 2 - 9 if digit > 4 else digit * 2
        total += digit
        double = not double
    return total % 10 == 0


def validate_card(form, today: date) -> dict:
    errors = {}
    number = re.sub(r"[ -]", "", form.get("card_number", ""))
    if not re.fullmatch(r"\d{13,19}", number) or not luhn_ok(number):
        errors["card_number"] = "Enter a valid card number."
    expiry = re.fullmatch(r"(\d{2})/(\d{2})", form.get("expiry", "").strip())
    if not expiry or not 1 <= int(expiry.group(1)) <= 12:
        errors["expiry"] = "Use the format MM/YY."
    elif (2000 + int(expiry.group(2)), int(expiry.group(1))) < (today.year, today.month):
        errors["expiry"] = "This card has expired."
    if not re.fullmatch(r"\d{3,4}", form.get("cvc", "")):
        errors["cvc"] = "Enter the 3 or 4 digit security code."
    return errors
