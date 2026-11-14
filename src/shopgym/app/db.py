"""SQLite schema, connections and password hashing (stdlib only)."""

import hashlib
import hmac
import secrets
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE users (
  id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
  password_hash TEXT NOT NULL, is_admin INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL);
CREATE TABLE sessions (
  token TEXT PRIMARY KEY, user_id INTEGER REFERENCES users(id), created_at TEXT NOT NULL);
CREATE TABLE categories (id INTEGER PRIMARY KEY, slug TEXT UNIQUE NOT NULL, name TEXT NOT NULL);
CREATE TABLE products (
  id INTEGER PRIMARY KEY, sku TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
  category_id INTEGER NOT NULL REFERENCES categories(id), price_cents INTEGER NOT NULL,
  stock INTEGER NOT NULL, description TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE reviews (
  id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(id),
  user_id INTEGER NOT NULL REFERENCES users(id), rating INTEGER NOT NULL,
  title TEXT NOT NULL, body TEXT NOT NULL, hidden INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL);
CREATE TABLE addresses (
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), label TEXT NOT NULL,
  full_name TEXT NOT NULL, line1 TEXT NOT NULL, city TEXT NOT NULL, postcode TEXT NOT NULL,
  country TEXT NOT NULL, is_default INTEGER NOT NULL DEFAULT 0);
CREATE TABLE orders (
  id INTEGER PRIMARY KEY, number INTEGER UNIQUE NOT NULL, user_id INTEGER REFERENCES users(id),
  email TEXT NOT NULL, status TEXT NOT NULL, subtotal_cents INTEGER NOT NULL,
  discount_cents INTEGER NOT NULL DEFAULT 0, shipping_cents INTEGER NOT NULL,
  total_cents INTEGER NOT NULL, coupon TEXT, ship_name TEXT NOT NULL, ship_line1 TEXT NOT NULL,
  ship_city TEXT NOT NULL, ship_postcode TEXT NOT NULL, ship_country TEXT NOT NULL,
  tracking_number TEXT, created_at TEXT NOT NULL);
CREATE TABLE order_items (
  id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES orders(id),
  product_id INTEGER NOT NULL REFERENCES products(id), product_name TEXT NOT NULL,
  unit_price_cents INTEGER NOT NULL, qty INTEGER NOT NULL);
CREATE TABLE order_events (
  id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES orders(id),
  created_at TEXT NOT NULL, message TEXT NOT NULL);
CREATE TABLE refunds (
  id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES orders(id),
  amount_cents INTEGER NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE coupons (code TEXT PRIMARY KEY, percent_off INTEGER NOT NULL, active INTEGER NOT NULL);
CREATE TABLE newsletter_subscribers (
  id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, active INTEGER NOT NULL,
  created_at TEXT NOT NULL);
CREATE TABLE cart_items (
  session_token TEXT NOT NULL REFERENCES sessions(token), product_id INTEGER NOT NULL
  REFERENCES products(id), qty INTEGER NOT NULL, PRIMARY KEY (session_token, product_id));
"""


def connect(path: Path | str, *, readonly: bool = False) -> sqlite3.Connection:
    """Open a connection with dict-like rows and FK enforcement."""
    uri = f"file:{Path(path)}?mode=ro" if readonly else str(path)
    conn = sqlite3.connect(uri, uri=readonly, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return f"pbkdf2${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    candidate = hash_password(password, bytes.fromhex(salt_hex))
    return hmac.compare_digest(candidate, stored)


def table_rows(conn: sqlite3.Connection, table: str) -> list[dict]:
    """All rows of a table as plain dicts, ordered by primary key (used for diffs and dumps)."""
    return [dict(r) for r in conn.execute(f"SELECT * FROM {table} ORDER BY rowid")]
