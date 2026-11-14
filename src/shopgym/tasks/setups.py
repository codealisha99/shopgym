"""Episode setup hooks. Run once on the fresh copy of the seed, before the initial snapshot is taken."""

import sqlite3
from typing import Any

from shopgym.config import SHOP_NOW

NOW = SHOP_NOW


def login_as(conn: sqlite3.Connection, session_token: str, *, email: str, **_: Any) -> None:
    conn.execute("UPDATE sessions SET user_id = (SELECT id FROM users WHERE email = ?) WHERE token = ?",
                 (email, session_token))


def cart(conn: sqlite3.Connection, session_token: str, *, items: list, **_: Any) -> None:
    for sku, qty in items:
        conn.execute("INSERT INTO cart_items(session_token, product_id, qty)"
                     " SELECT ?, id, ? FROM products WHERE sku = ?", (session_token, qty, sku))


def review(conn: sqlite3.Connection, session_token: str, *, sku: str, email: str, rating: int,
           title: str, body: str, **_: Any) -> None:
    conn.execute(
        "INSERT INTO reviews(product_id, user_id, rating, title, body, created_at)"
        " SELECT p.id, u.id, ?, ?, ?, ? FROM products p, users u WHERE p.sku = ? AND u.email = ?",
        (rating, title, body, NOW, sku, email))


SETUPS = {"login_as": login_as, "cart": cart, "review": review}
