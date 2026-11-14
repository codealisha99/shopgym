"""Product search and pagination. Shared by the storefront and by task checkers (ground truth)."""

import math
import re
import sqlite3

_BASE = """
SELECT * FROM (
  SELECT p.id, p.sku, p.name, p.price_cents, p.stock, p.description, p.active,
         c.slug AS category_slug, c.name AS category_name,
         (SELECT ROUND(AVG(r.rating), 1) FROM reviews r WHERE r.product_id = p.id AND r.hidden = 0) AS avg_rating,
         (SELECT COUNT(*) FROM reviews r WHERE r.product_id = p.id AND r.hidden = 0) AS review_count
  FROM products p JOIN categories c ON c.id = p.category_id
) WHERE active = 1
"""
SORTS = {
    "price_asc": "price_cents ASC, id ASC",
    "price_desc": "price_cents DESC, id ASC",
    "name": "name COLLATE NOCASE ASC",
    "rating": "COALESCE(avg_rating, 0) DESC, id ASC",
}


def search_products(conn: sqlite3.Connection, *, q: str = "", category: str = "",
                    max_price_cents: int | None = None, min_rating: float | None = None,
                    in_stock_only: bool = False, sort: str = "name") -> list[sqlite3.Row]:
    """Filter the active catalogue. Text match is case-insensitive over name and description."""
    clauses, params = [], []
    if q.strip():
        clauses.append("(name LIKE ? OR description LIKE ?)")
        params += [f"%{q.strip()}%"] * 2
    if category:
        clauses.append("category_slug = ?")
        params.append(category)
    if max_price_cents is not None:
        clauses.append("price_cents <= ?")
        params.append(max_price_cents)
    if min_rating is not None:
        clauses.append("COALESCE(avg_rating, 0) >= ?")
        params.append(min_rating)
    if in_stock_only:
        clauses.append("stock > 0")
    where = "".join(f" AND {c}" for c in clauses)
    order = SORTS.get(sort, SORTS["name"])
    return conn.execute(f"{_BASE} {where} ORDER BY {order}", params).fetchall()


def paginate(items: list, page: int, size: int) -> tuple[list, int]:
    """Return (page slice, page count). Page numbers are 1-based and clamped to the valid range."""
    pages = max(1, math.ceil(len(items) / size))
    page = min(max(page, 1), pages)
    return items[(page - 1) * size: page * size], pages


def parse_page(raw: str | None) -> int:
    return int(raw) if raw and re.fullmatch(r"\d{1,6}", raw) else 1


def product_by_sku(conn: sqlite3.Connection, sku: str) -> sqlite3.Row | None:
    rows = conn.execute(f"{_BASE} AND sku = ?", (sku,)).fetchall()
    return rows[0] if rows else None
