"""Programmatic checkers.

A checker never looks at the trajectory. It compares two database states (the snapshot taken
after task setup, and the live database at the end) and optionally the agent's final answer.
Every mutating checker also calls `assert_only`, so an unrelated write (cancelling the wrong
order, refunding the wrong customer) fails the task even if the target change happened.
"""

import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shopgym.app.catalog import search_products
from shopgym.app.db import connect, table_rows, verify_password

IGNORED_TABLES = {"sessions", "order_events"}  # session bookkeeping and audit logs
NATURAL_KEYS = {"orders": "number", "products": "sku", "users": "email", "categories": "slug",
                "newsletter_subscribers": "email", "coupons": "code"}
WILDCARD = "*"


@dataclass(frozen=True)
class CheckContext:
    initial: Path
    final: Path
    answer: str | None


@dataclass(frozen=True)
class Verdict:
    ok: bool
    reason: str


Checker = Callable[..., Verdict]
CHECKERS: dict[str, Checker] = {}


def checker(name: str) -> Callable[[Checker], Checker]:
    def register(fn: Checker) -> Checker:
        CHECKERS[name] = fn
        return fn
    return register


def _ro(path: Path) -> sqlite3.Connection:
    return connect(path, readonly=True)


def _key(table: str, row: dict) -> Any:
    if table == "cart_items":
        return (row["session_token"], row["product_id"])
    return row[NATURAL_KEYS[table]] if table in NATURAL_KEYS else row["id"]


def _rows(conn: sqlite3.Connection, table: str) -> dict:
    return {_key(table, r): r for r in table_rows(conn, table)}


def _all_tables(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]


def changed_keys(ctx: CheckContext) -> dict[str, set]:
    """Map table -> keys of rows that were added, removed or modified."""
    before, after = _ro(ctx.initial), _ro(ctx.final)
    try:
        result = {}
        for table in _all_tables(before):
            if table in IGNORED_TABLES:
                continue
            old, new = _rows(before, table), _rows(after, table)
            keys = {k for k in old.keys() | new.keys() if old.get(k) != new.get(k)}
            if keys:
                result[table] = keys
        return result
    finally:
        before.close()
        after.close()


def assert_only(ctx: CheckContext, allowed: dict) -> Verdict:
    """Pass only if every changed row is explicitly allowed. WILDCARD allows any row of a table."""
    unexpected = []
    for table, keys in changed_keys(ctx).items():
        permitted = allowed.get(table, set())
        if permitted == WILDCARD:
            continue
        unexpected += [f"{table}:{k}" for k in sorted(map(str, keys - set(permitted)))]
    if unexpected:
        return Verdict(False, f"unexpected side effects: {', '.join(unexpected[:6])}")
    return Verdict(True, "no unexpected changes")


def _number_answer(answer: str | None) -> int | None:
    if answer is None:
        return None
    numbers = re.findall(r"\d+", answer)
    return int(numbers[0]) if len(numbers) == 1 else None


def _text_answer(answer: str | None) -> str:
    return (answer or "").strip().strip(".").strip().lower()


def _cart_lines(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute("SELECT p.sku, c.qty FROM cart_items c JOIN products p ON p.id = c.product_id").fetchall()
    return {r["sku"]: r["qty"] for r in rows}


def _cheapest_in_stock(conn: sqlite3.Connection, category: str) -> list[str]:
    rows = search_products(conn, category=category, in_stock_only=True, sort="price_asc")
    if not rows:
        return []
    best = rows[0]["price_cents"]
    return [r["name"] for r in rows if r["price_cents"] == best]


def _expect(condition: bool, ok: str, bad: str) -> Verdict:
    return Verdict(True, ok) if condition else Verdict(False, bad)


# ---- read-only answer checkers -------------------------------------------------------------

@checker("search_count")
def search_count(ctx: CheckContext, query: str, **_: Any) -> Verdict:
    expected = len(search_products(_ro(ctx.initial), q=query))
    got = _number_answer(ctx.answer)
    return _expect(got == expected, f"count {expected}", f"expected {expected}, answered {ctx.answer!r}")


@checker("product_price")
def product_price(ctx: CheckContext, sku: str, **_: Any) -> Verdict:
    row = _ro(ctx.initial).execute("SELECT price_cents FROM products WHERE sku = ?", (sku,)).fetchone()
    numbers = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", ctx.answer or "")]
    expected = row["price_cents"] / 100
    ok = len(numbers) == 1 and abs(numbers[0] - expected) < 0.005
    return _expect(ok, "price matches", f"expected {expected:.2f}, answered {ctx.answer!r}")


@checker("cheapest_in_stock")
def cheapest_in_stock(ctx: CheckContext, category: str, **_: Any) -> Verdict:
    names = [n.lower() for n in _cheapest_in_stock(_ro(ctx.initial), category)]
    return _expect(_text_answer(ctx.answer) in names, "cheapest name", f"expected one of {names}")


@checker("count_best_reviews")
def count_best_reviews(ctx: CheckContext, sku: str, word: str = "best", **_: Any) -> Verdict:
    conn = _ro(ctx.initial)
    bodies = conn.execute(
        "SELECT r.title, r.body FROM reviews r JOIN products p ON p.id = r.product_id"
        " WHERE p.sku = ? AND r.hidden = 0", (sku,)).fetchall()
    pattern = re.compile(rf"\b{re.escape(word)}\b", re.IGNORECASE)
    expected = sum(1 for r in bodies if pattern.search(r["body"]) or pattern.search(r["title"]))
    got = _number_answer(ctx.answer)
    return _expect(got == expected, f"count {expected}", f"expected {expected}, answered {ctx.answer!r}")


@checker("order_status_answer")
def order_status_answer(ctx: CheckContext, number: int, **_: Any) -> Verdict:
    status = _ro(ctx.initial).execute("SELECT status FROM orders WHERE number = ?", (number,)).fetchone()["status"]
    return _expect(_text_answer(ctx.answer) == status, "status matches", f"expected {status!r}")


@checker("sku_answer")
def sku_answer(ctx: CheckContext, name: str, **_: Any) -> Verdict:
    sku = _ro(ctx.initial).execute("SELECT sku FROM products WHERE name = ?", (name,)).fetchone()["sku"]
    return _expect(_text_answer(ctx.answer).upper() == sku, "sku matches", f"expected {sku}")


@checker("multi_filter_count")
def multi_filter_count(ctx: CheckContext, category: str, max_dollars: int, min_rating: float, **_: Any) -> Verdict:
    rows = search_products(_ro(ctx.initial), category=category, max_price_cents=max_dollars * 100,
                           min_rating=min_rating)
    got = _number_answer(ctx.answer)
    return _expect(got == len(rows), f"count {len(rows)}", f"expected {len(rows)}, answered {ctx.answer!r}")


@checker("admin_subscriber_count")
def admin_subscriber_count(ctx: CheckContext, **_: Any) -> Verdict:
    expected = _ro(ctx.initial).execute("SELECT COUNT(*) FROM newsletter_subscribers WHERE active = 1").fetchone()[0]
    got = _number_answer(ctx.answer)
    return _expect(got == expected, f"count {expected}", f"expected {expected}, answered {ctx.answer!r}")


@checker("cancel_refusal")
def cancel_refusal(ctx: CheckContext, number: int, **_: Any) -> Verdict:
    said_no = re.search(r"not\s+(be\s+)?cancel", ctx.answer or "", re.IGNORECASE) is not None
    if not said_no:
        return Verdict(False, "answer must say the order cannot be cancelled")
    before = _rows(_ro(ctx.initial), "orders")[number]["status"]
    after = _rows(_ro(ctx.final), "orders")[number]["status"]
    if after != before:
        return Verdict(False, f"order {number} changed from {before} to {after}")
    return assert_only(ctx, {})


# ---- cart ----------------------------------------------------------------------------------

@checker("cart_equals")
def cart_equals(ctx: CheckContext, lines: dict, **_: Any) -> Verdict:
    got = _cart_lines(_ro(ctx.final))
    if got != lines:
        return Verdict(False, f"cart is {got}, expected {lines}")
    return assert_only(ctx, {"cart_items": WILDCARD})


@checker("cheapest_add_to_cart")
def cheapest_add_to_cart(ctx: CheckContext, category: str, qty: int, **_: Any) -> Verdict:
    names = _cheapest_in_stock(_ro(ctx.initial), category)
    if len(names) != 1:
        return Verdict(False, f"ambiguous or empty cheapest set {names}")
    sku = _ro(ctx.initial).execute("SELECT sku FROM products WHERE name = ?", (names[0],)).fetchone()["sku"]
    return cart_equals(ctx, lines={sku: qty})


# ---- customer account ----------------------------------------------------------------------

@checker("newsletter_subscribe")
def newsletter_subscribe(ctx: CheckContext, email: str, **_: Any) -> Verdict:
    row = _rows(_ro(ctx.final), "newsletter_subscribers").get(email)
    if row is None or row["active"] != 1:
        return Verdict(False, f"{email} is not an active subscriber")
    return assert_only(ctx, {"newsletter_subscribers": {email}})


@checker("newsletter_unsubscribe")
def newsletter_unsubscribe(ctx: CheckContext, email: str, **_: Any) -> Verdict:
    row = _rows(_ro(ctx.final), "newsletter_subscribers").get(email)
    if row is None or row["active"] != 0:
        return Verdict(False, f"{email} is still subscribed")
    return assert_only(ctx, {"newsletter_subscribers": {email}})


@checker("register_account")
def register_account(ctx: CheckContext, email: str, name: str, password: str, **_: Any) -> Verdict:
    user = _rows(_ro(ctx.final), "users").get(email)
    if user is None or user["name"] != name or not verify_password(password, user["password_hash"]):
        return Verdict(False, "no matching account with that name and password")
    return assert_only(ctx, {"users": {email}})


@checker("update_profile_name")
def update_profile_name(ctx: CheckContext, email: str, name: str, password: str, **_: Any) -> Verdict:
    user = _rows(_ro(ctx.final), "users").get(email)
    if user is None or user["name"] != name:
        return Verdict(False, f"name is {user and user['name']!r}, expected {name!r}")
    if not verify_password(password, user["password_hash"]):
        return Verdict(False, "password was changed by mistake")
    return assert_only(ctx, {"users": {email}})


@checker("add_address")
def add_address(ctx: CheckContext, email: str, label: str, full_name: str, line1: str, city: str,
                postcode: str, **_: Any) -> Verdict:
    conn = _ro(ctx.final)
    rows = conn.execute("SELECT a.* FROM addresses a JOIN users u ON u.id = a.user_id WHERE u.email = ?",
                        (email,)).fetchall()
    match = [r for r in rows if (r["label"], r["full_name"], r["line1"], r["city"], r["postcode"]) ==
             (label, full_name, line1, city, postcode)]
    defaults = [r for r in rows if r["is_default"] == 1]
    if not match or match[0]["is_default"] != 1:
        return Verdict(False, "new address is missing or not the default")
    if len(defaults) != 1:
        return Verdict(False, f"expected one default address, found {len(defaults)}")
    return assert_only(ctx, {"addresses": WILDCARD})


@checker("write_review")
def write_review(ctx: CheckContext, sku: str, email: str, rating: int, must_contain: str, **_: Any) -> Verdict:
    old_ids = set(_rows(_ro(ctx.initial), "reviews"))
    new = [r for r in table_rows(_ro(ctx.final), "reviews") if r["id"] not in old_ids]
    conn = _ro(ctx.final)
    for row in new:
        product = conn.execute("SELECT sku FROM products WHERE id = ?", (row["product_id"],)).fetchone()["sku"]
        author = conn.execute("SELECT email FROM users WHERE id = ?", (row["user_id"],)).fetchone()["email"]
        if product == sku and author == email and row["rating"] == rating and must_contain.lower() in row["body"].lower():
            return assert_only(ctx, {"reviews": WILDCARD})
    return Verdict(False, f"no new {rating}-star review of {sku} by {email} containing {must_contain!r}")


@checker("cancel_order")
def cancel_order(ctx: CheckContext, number: int, **_: Any) -> Verdict:
    row = _rows(_ro(ctx.final), "orders").get(number)
    if row is None or row["status"] != "cancelled":
        return Verdict(False, f"order {number} is {row and row['status']}, expected cancelled")
    return assert_only(ctx, {"orders": {number}})


@checker("change_shipping_address")
def change_shipping_address(ctx: CheckContext, number: int, full_name: str, line1: str, city: str,
                            postcode: str, **_: Any) -> Verdict:
    row = _rows(_ro(ctx.final), "orders").get(number)
    wanted = (full_name, line1, city, postcode)
    if row is None or (row["ship_name"], row["ship_line1"], row["ship_city"], row["ship_postcode"]) != wanted:
        return Verdict(False, f"order {number} does not have the new shipping address")
    return assert_only(ctx, {"orders": {number}})


@checker("guest_checkout")
def guest_checkout(ctx: CheckContext, sku: str, qty: int, email: str, full_name: str, line1: str, city: str,
                   postcode: str, coupon: str | None = None, percent: int | None = None, **_: Any) -> Verdict:
    before, after = _ro(ctx.initial), _ro(ctx.final)
    old_numbers = set(_rows(before, "orders"))
    new_orders = [r for r in table_rows(after, "orders") if r["number"] not in old_numbers]
    if len(new_orders) != 1:
        return Verdict(False, f"expected exactly one new order, found {len(new_orders)}")
    order = new_orders[0]
    product = after.execute("SELECT * FROM products WHERE sku = ?", (sku,)).fetchone()
    items = after.execute("SELECT product_id, qty FROM order_items WHERE order_id = ?", (order["id"],)).fetchall()
    if [(i["product_id"], i["qty"]) for i in items] != [(product["id"], qty)]:
        return Verdict(False, "order items do not match the requested product and quantity")
    subtotal = product["price_cents"] * qty
    discount = round(subtotal * percent / 100) if percent else 0
    checks = [
        (order["email"] == email, "order email is wrong"),
        (order["status"] == "processing", "new order is not processing"),
        ((order["ship_name"], order["ship_line1"], order["ship_city"], order["ship_postcode"]) ==
         (full_name, line1, city, postcode), "shipping address is wrong"),
        ((order["coupon"] or "") == (coupon or ""), "coupon not recorded"),
        (order["discount_cents"] == discount, f"discount should be {discount} cents"),
        (order["total_cents"] == order["subtotal_cents"] - order["discount_cents"] + order["shipping_cents"],
         "order total does not add up"),
        (order["subtotal_cents"] == subtotal, "subtotal is wrong"),
        (product["stock"] == before.execute("SELECT stock FROM products WHERE sku = ?", (sku,)).fetchone()["stock"] - qty,
         "stock was not reduced by the quantity"),
    ]
    for passed, message in checks:
        if not passed:
            return Verdict(False, message)
    return assert_only(ctx, {"orders": WILDCARD, "order_items": WILDCARD, "products": {sku},
                             "cart_items": WILDCARD})


# ---- admin ---------------------------------------------------------------------------------

@checker("admin_refund_order")
def admin_refund_order(ctx: CheckContext, number: int, **_: Any) -> Verdict:
    row = _rows(_ro(ctx.final), "orders").get(number)
    if row is None or row["status"] != "refunded":
        return Verdict(False, f"order {number} is not refunded")
    refunds = [r for r in table_rows(_ro(ctx.final), "refunds") if r["order_id"] == row["id"]]
    if len(refunds) != 1 or refunds[0]["amount_cents"] != row["total_cents"]:
        return Verdict(False, "refund record for the full total is missing")
    return assert_only(ctx, {"orders": {number}, "refunds": WILDCARD})


@checker("admin_set_stock")
def admin_set_stock(ctx: CheckContext, sku: str, stock: int, **_: Any) -> Verdict:
    row = _rows(_ro(ctx.final), "products").get(sku)
    if row is None or row["stock"] != stock:
        return Verdict(False, f"stock for {sku} is {row and row['stock']}, expected {stock}")
    return assert_only(ctx, {"products": {sku}})


@checker("admin_mark_shipped")
def admin_mark_shipped(ctx: CheckContext, number: int, tracking: str, **_: Any) -> Verdict:
    row = _rows(_ro(ctx.final), "orders").get(number)
    if row is None or row["status"] != "shipped" or row["tracking_number"] != tracking:
        return Verdict(False, f"order {number} is not shipped with tracking {tracking}")
    return assert_only(ctx, {"orders": {number}})


@checker("admin_hide_review")
def admin_hide_review(ctx: CheckContext, title: str, **_: Any) -> Verdict:
    target = [r for r in table_rows(_ro(ctx.initial), "reviews") if r["title"] == title]
    if len(target) != 1:
        return Verdict(False, f"setup problem: {len(target)} reviews titled {title!r}")
    final = _rows(_ro(ctx.final), "reviews")[target[0]["id"]]
    if final["hidden"] != 1:
        return Verdict(False, "the bad review is still visible")
    return assert_only(ctx, {"reviews": {target[0]["id"]}})
