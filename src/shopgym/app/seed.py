"""Deterministic seed data.

Anchor entities (named customers, orders #1042 etc.) are fixed so tasks can refer to them.
Filler data is drawn from random.Random(seed), so the same seed always builds the same bytes.
"""

import hashlib
import random
from pathlib import Path

from shopgym.app.db import SCHEMA, connect, hash_password
from shopgym.config import DEMO_PASSWORD

CATEGORIES = [
    ("clothing", "Clothing"), ("home", "Home"), ("garden", "Garden"),
    ("books", "Books"), ("electronics", "Electronics"), ("toys", "Toys"),
]
# (sku, name, category slug, price cents, stock, description)
ANCHOR_PRODUCTS = [
    ("CLO-TRP-01", "Trail Runner Pro", "clothing", 12900, 20, "Lightweight trail shoe with a grippy six-lug sole."),
    ("CLO-TOT-02", "Canvas Tote", "clothing", 2400, 35, "Heavy waxed canvas tote with leather handles."),
    ("HOM-PO-01", "Ceramic Pour-Over Set", "home", 4200, 12, "Stoneware dripper and carafe for slow coffee."),
    ("HOM-LMP-02", "Brass Desk Lamp", "home", 8900, 6, "Adjustable reading lamp with a warm LED bulb."),
    ("GAR-HOSE-30", "30m Garden Hose", "garden", 3600, 18, "Kink-resistant hose with a brass fitting."),
    ("BOK-ATL-01", "Field Notes Atlas", "books", 1800, 40, "Pocket atlas of coastlines and trail maps."),
    ("ELE-EAR-01", "Wireless Earbuds Lite", "electronics", 5900, 9, "Small earbuds with a 20 hour case battery."),
]
FILLER_NOUNS = {
    "clothing": ["Rain Shell", "Merino Socks", "Wool Beanie", "Canvas Apron", "Chore Jacket", "Linen Shirt", "Fleece Vest"],
    "home": ["Cast Iron Skillet", "Linen Throw", "Oak Board", "Stoneware Mug", "Bookends", "Wool Rug", "Glass Carafe"],
    "garden": ["Pruning Shears", "Planter", "Herb Keeper", "Watering Can", "Bulb Planter", "Kneeling Pad", "Compost Bin"],
    "books": ["Field Guide to Birds", "Paper Almanac", "Ink Journal", "Sketchbook", "Map Set", "Soup Cookbook"],
    "electronics": ["USB-C Hub", "Desk Speaker", "Action Camera", "Power Bank", "Smart Plug", "Keyboard", "Webcam"],
    "toys": ["Wooden Train", "Puzzle 500pc", "Kite Kit", "Chess Set", "Building Blocks", "Plush Fox", "Magnet Tiles"],
}
ADJECTIVES = ["Classic", "Compact", "Deluxe", "Everyday", "Heritage", "Mini", "Pro", "Field"]
REVIEW_BODIES = [
    "Solid build and it does the job.", "Honestly the best one I have owned.",
    "Best value in this category, no question.", "Arrived late but works fine.",
    "Not what I expected, so I returned it.", "Would buy again. Best purchase this year.",
    "Fit runs a little small.", "Great for weekend trips.", "Good, though the packaging was bulky.",
    "Works well with everything else I own.", "The best thing I bought for the garden this spring.",
    "Decent for the price.",
]
FIRST_NAMES = ["Mira", "Owen", "Priya", "Lars", "Noor", "Tomas", "Ines", "Kenji", "Ruth", "Samir", "Elif", "Jonah", "Dara", "Felix"]
LAST_NAMES = ["Okafor", "Brandt", "Lindqvist", "Ramos", "Haddad", "Novak", "Sato", "Quinn", "Moreau", "Adeyemi", "Kowalski", "Tanaka"]
ANCHOR_USERS = [  # email, name, is_admin, address line, city, postcode
    ("admin@shop.test", "Store Admin", 1, "1 Warehouse Way", "London", "E1 6AN"),
    ("ada@shop.test", "Ada Lovelace", 0, "12 St James's Square", "London", "SW1Y 4JH"),
    ("grace@shop.test", "Grace Hopper", 0, "4 Mill Lane", "Leeds", "LS1 4AP"),
    ("alan@shop.test", "Alan Turing", 0, "9 Bletchley Road", "Bletchley", "MK3 6EB"),
    ("hedy@shop.test", "Hedy Lamarr", 0, "77 Canal Street", "Manchester", "M1 3HE"),
    ("hedy.lamarr@mail.test", "Hedy Lamarr", 0, "3 Harbour View", "Bristol", "BS1 5TR"),
]
# number, customer email (None for filler), status, created_at, [(sku, qty)], tracking
ANCHOR_ORDERS = [
    (1042, "ada@shop.test", "processing", "2026-03-01T10:12:00", [("CLO-TRP-01", 1), ("CLO-TOT-02", 1)], None),
    (1043, "ada@shop.test", "processing", "2026-03-05T18:40:00", [("BOK-ATL-01", 2)], None),
    (1044, "ada@shop.test", "shipped", "2026-02-10T09:05:00", [("ELE-EAR-01", 1)], "1Z84E0120312345678"),
    (1051, "grace@shop.test", "delivered", "2026-02-20T14:22:00", [("HOM-PO-01", 1)], "1Z84E0120398765432"),
    (1061, "hedy@shop.test", "delivered", "2026-03-02T08:30:00", [("HOM-LMP-02", 1)], "1Z84E0120311112222"),
    (1062, "hedy.lamarr@mail.test", "delivered", "2026-03-08T16:00:00", [("HOM-LMP-02", 1), ("BOK-ATL-01", 1)], "1Z84E0120322223333"),
]
FILLER_ORDER_NUMBERS = [n for n in range(1001, 1071) if n not in {o[0] for o in ANCHOR_ORDERS}]
FILLER_STATUSES = ["delivered", "shipped", "processing", "cancelled", "refunded"]


def _salt(text: str) -> bytes:
    return hashlib.sha256(text.encode()).digest()[:16]


def _password(email: str) -> str:
    return hash_password(DEMO_PASSWORD, _salt(email))


def _filler_products(rng: random.Random, taken: set[str]) -> list[tuple]:
    rows = []
    for slug, _ in CATEGORIES:
        names = set()
        for idx, noun in enumerate(FILLER_NOUNS[slug]):
            name = f"{rng.choice(ADJECTIVES)} {noun}"
            if name in names or name in taken:
                name = f"{noun} No. {idx + 2}"
            names.add(name)
            taken.add(name)
            price = rng.randint(9, 199) * 100 + rng.choice([0, 49, 99])
            stock = 0 if rng.random() < 0.15 else rng.randint(3, 40)
            sku = f"{slug[:3].upper()}-F{len(rows) + 1:03d}"
            rows.append((sku, name, slug, price, stock, f"{name}. Ships in two working days."))
    return rows


def _insert_categories(conn) -> dict[str, int]:
    conn.executemany("INSERT INTO categories(slug, name) VALUES (?, ?)", CATEGORIES)
    return {row["slug"]: row["id"] for row in conn.execute("SELECT id, slug FROM categories")}


def _insert_users(conn, rng: random.Random) -> dict[str, int]:
    users = list(ANCHOR_USERS)
    for i in range(14):
        first, last = FIRST_NAMES[i], rng.choice(LAST_NAMES)
        email = f"{first.lower()}.{last.lower()}{i}@example.test"
        users.append((email, f"{first} {last}", 0, f"{10 + i} High Street", "Oxford", f"OX{i + 1} 1AA"))
    for email, name, admin, _, _, _ in users:
        conn.execute("INSERT INTO users(email, name, password_hash, is_admin, created_at) VALUES (?,?,?,?,?)",
                     (email, name, _password(email), admin, "2025-11-01T09:00:00"))
    ids = {r["email"]: r["id"] for r in conn.execute("SELECT id, email FROM users")}
    for email, name, _, line1, city, postcode in users:
        conn.execute(
            "INSERT INTO addresses(user_id, label, full_name, line1, city, postcode, country, is_default)"
            " VALUES (?, 'Home', ?, ?, ?, ?, 'United Kingdom', 1)",
            (ids[email], name, line1, city, postcode))
    return ids


def _insert_products(conn, rng: random.Random, cat_ids: dict[str, int]) -> dict[str, int]:
    taken = {p[1] for p in ANCHOR_PRODUCTS}
    rows = list(ANCHOR_PRODUCTS) + _filler_products(rng, taken)
    for sku, name, slug, price, stock, desc in rows:
        conn.execute("INSERT INTO products(sku, name, category_id, price_cents, stock, description)"
                     " VALUES (?,?,?,?,?,?)", (sku, name, cat_ids[slug], price, stock, desc))
    return {r["sku"]: r["id"] for r in conn.execute("SELECT id, sku FROM products")}


def _insert_reviews(conn, rng: random.Random, product_ids, user_ids) -> None:
    customer_ids = [v for k, v in user_ids.items() if k != "admin@shop.test"]
    for sku, pid in product_ids.items():
        count = 13 if sku == "CLO-TRP-01" else rng.randint(0, 9)
        for _ in range(count):
            conn.execute(
                "INSERT INTO reviews(product_id, user_id, rating, title, body, created_at) VALUES (?,?,?,?,?,?)",
                (pid, rng.choice(customer_ids), rng.randint(1, 5), "Review",
                 rng.choice(REVIEW_BODIES), f"2026-01-{rng.randint(1, 28):02d}T12:00:00"))


def _insert_order(conn, number, user_id, email, status, created, lines, tracking, pids):
    prices = {r["id"]: r for r in conn.execute("SELECT id, name, price_cents FROM products")}
    subtotal = 0
    items = []
    for sku, qty in lines:
        p = prices[pids[sku]]
        subtotal += p["price_cents"] * qty
        items.append((pids[sku], p["name"], p["price_cents"], qty))
    shipping = 0 if subtotal >= 5000 else 499
    addr = conn.execute("SELECT full_name, line1, city, postcode, country FROM addresses"
                        " WHERE user_id IS ? AND is_default = 1", (user_id,)).fetchone()
    if addr is None:  # guest order: shipping details are placeholders
        addr = {"full_name": "Guest Customer", "line1": "1 Guest Street", "city": "Reading",
                "postcode": "RG1 1AA", "country": "United Kingdom"}
    cur = conn.execute(
        "INSERT INTO orders(number, user_id, email, status, subtotal_cents, shipping_cents, total_cents,"
        " ship_name, ship_line1, ship_city, ship_postcode, ship_country, tracking_number, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (number, user_id, email, status, subtotal, shipping, subtotal + shipping, addr["full_name"],
         addr["line1"], addr["city"], addr["postcode"], addr["country"], tracking, created))
    conn.executemany("INSERT INTO order_items(order_id, product_id, product_name, unit_price_cents, qty)"
                     " VALUES (?,?,?,?,?)", [(cur.lastrowid, *it) for it in items])
    conn.execute("INSERT INTO order_events(order_id, created_at, message) VALUES (?,?,?)",
                 (cur.lastrowid, created, f"Order placed (status {status})"))
    return cur.lastrowid


def _insert_orders(conn, rng: random.Random, user_ids, product_ids) -> None:
    for number, email, status, created, lines, tracking in ANCHOR_ORDERS:
        _insert_order(conn, number, user_ids[email], email, status, created, lines, tracking, product_ids)
    filler_skus = list(product_ids)
    customers = [(v, k) for k, v in user_ids.items() if k.endswith("@example.test")]
    for number in FILLER_ORDER_NUMBERS:
        uid, email = rng.choice(customers + [(None, "guest@example.test")])
        lines = [(rng.choice(filler_skus), rng.randint(1, 2)) for _ in range(rng.randint(1, 3))]
        lines = list({sku: (sku, q) for sku, q in lines}.values())
        created = f"2026-0{rng.randint(1, 3)}-{rng.randint(1, 28):02d}T{rng.randint(8, 20):02d}:00:00"
        _insert_order(conn, number, uid, email, rng.choice(FILLER_STATUSES), created, lines, None, product_ids)


def _insert_misc(conn, rng: random.Random, user_ids) -> None:
    conn.executemany("INSERT INTO coupons(code, percent_off, active) VALUES (?,?,?)",
                     [("SPRING10", 10, 1), ("EXPIRED20", 20, 0)])
    subscribers = [("ada@shop.test", 1)] + [(f"sub{i}@example.test", rng.choice([0, 1, 1])) for i in range(12)]
    conn.executemany("INSERT INTO newsletter_subscribers(email, active, created_at) VALUES (?,?,?)",
                     [(e, a, "2026-01-15T10:00:00") for e, a in subscribers])


def build_database(path: Path | str, seed: int) -> Path:
    """Create a fresh, fully populated database file. Same seed -> identical rows."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    rng = random.Random(seed)
    conn = connect(path)
    try:
        conn.executescript(SCHEMA)
        cat_ids = _insert_categories(conn)
        user_ids = _insert_users(conn, rng)
        product_ids = _insert_products(conn, rng, cat_ids)
        _insert_reviews(conn, rng, product_ids, user_ids)
        _insert_orders(conn, rng, user_ids, product_ids)
        _insert_misc(conn, rng, user_ids)
        conn.commit()
    finally:
        conn.close()
    return path
