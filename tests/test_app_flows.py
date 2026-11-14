"""Key storefront, account and admin flows, exercised over HTTP with no browser."""

from starlette.testclient import TestClient

from shopgym.app.catalog import search_products
from shopgym.app.db import connect
from shopgym.app.server import make_app
from shopgym.env.episodes import create_episode

CARD = {"card_number": "4242 4242 4242 4242", "expiry": "12/30", "cvc": "123"}
SHIP = {"full_name": "Test Buyer", "line1": "1 Test Road", "city": "Leeds", "postcode": "LS1 1AA",
        "country": "United Kingdom"}


def db(client):
    return connect(client.episode.db)


def login(client, email, password="password123"):
    return client.post("/login", data={"email": email, "password": password})


def test_home_and_catalogue_render(client):
    assert "Gear that outlasts the trip" in client.get("/").text
    assert "Trail Runner Pro" in client.get("/products?q=trail").text


def test_search_matches_shared_catalog_query(client):
    expected = search_products(db(client), q="lamp")
    assert f"{len(expected)} found" in client.get("/products?q=lamp").text


def test_guest_checkout_places_order_and_takes_stock(client):
    stock_before = db(client).execute("SELECT stock FROM products WHERE sku='CLO-TRP-01'").fetchone()[0]
    assert client.post("/cart/add", data={"sku": "CLO-TRP-01", "qty": "2"}).status_code == 303
    assert client.post("/checkout/shipping", data={**SHIP, "email": "guest@example.test"}).status_code == 200
    review = client.post("/checkout/payment", data={**SHIP, "email": "guest@example.test", **CARD, "coupon": "SPRING10"})
    assert review.status_code == 200 and "Place order" in review.text
    placed = client.post("/checkout/place", data={**SHIP, "email": "guest@example.test", "coupon": "SPRING10"})
    assert placed.status_code == 303 and placed.headers["location"].startswith("/checkout/complete/")
    conn = db(client)
    number = placed.headers["location"].rsplit("/", 1)[-1]
    order = conn.execute("SELECT * FROM orders WHERE number = ?", (number,)).fetchone()
    assert order["email"] == "guest@example.test"
    assert order["subtotal_cents"] == 2 * 12900 and order["discount_cents"] == 2580
    assert order["total_cents"] == order["subtotal_cents"] - order["discount_cents"]  # free shipping over $50
    assert conn.execute("SELECT stock FROM products WHERE sku='CLO-TRP-01'").fetchone()[0] == stock_before - 2
    assert conn.execute("SELECT COUNT(*) FROM cart_items").fetchone()[0] == 0


def test_payment_validation_blocks_bad_card_and_expired_card(client):
    client.post("/cart/add", data={"sku": "BOK-ATL-01", "qty": "1"})
    bad = client.post("/checkout/payment", data={**SHIP, "email": "a@b.test", "card_number": "4242 4242 4242 4241",
                                                  "expiry": "12/30", "cvc": "123"})
    assert bad.status_code == 422 and "valid card number" in bad.text
    expired = client.post("/checkout/payment", data={**SHIP, "email": "a@b.test", **CARD, "expiry": "01/20"})
    assert expired.status_code == 422 and "expired" in expired.text
    assert db(client).execute("SELECT COUNT(*) FROM orders WHERE email='a@b.test'").fetchone()[0] == 0


def test_cannot_add_more_than_stock(client):
    stock = db(client).execute("SELECT stock FROM products WHERE sku='HOM-LMP-02'").fetchone()[0]
    resp = client.post("/cart/add", data={"sku": "HOM-LMP-02", "qty": str(stock + 1)})
    assert resp.status_code == 303 and "/products/HOM-LMP-02" in resp.headers["location"]
    assert db(client).execute("SELECT COUNT(*) FROM cart_items").fetchone()[0] == 0


def test_login_rejects_wrong_password_and_accepts_right_one(client):
    assert login(client, "ada@shop.test", "wrong").status_code == 422
    ok = login(client, "ada@shop.test")
    assert ok.status_code == 303 and ok.headers["location"].startswith("/account")
    assert "Hello, Ada Lovelace" in client.get("/account").text


def test_customer_can_cancel_own_processing_order_only(client):
    login(client, "ada@shop.test")
    assert client.post("/account/orders/1042/cancel").status_code == 303
    assert db(client).execute("SELECT status FROM orders WHERE number=1042").fetchone()[0] == "cancelled"
    assert db(client).execute("SELECT status FROM orders WHERE number=1043").fetchone()[0] == "processing"
    assert client.get("/account/orders/1051").status_code == 404  # Grace's order, not Ada's
    client.post("/account/orders/1044/cancel")  # shipped: refused, no change
    assert db(client).execute("SELECT status FROM orders WHERE number=1044").fetchone()[0] == "shipped"


def test_change_address_on_editable_order(client):
    login(client, "ada@shop.test")
    resp = client.post("/account/orders/1043/address", data={**SHIP})
    assert resp.status_code == 303
    row = db(client).execute("SELECT ship_name, ship_city FROM orders WHERE number=1043").fetchone()
    assert (row["ship_name"], row["ship_city"]) == ("Test Buyer", "Leeds")


def test_admin_area_is_gated(client):
    assert client.get("/admin").status_code in (303, 403)
    login(client, "ada@shop.test")
    assert client.get("/admin/orders").status_code == 403


def test_admin_refund_creates_refund_row(client):
    login(client, "admin@shop.test")
    assert client.post("/admin/orders/1051/refund").status_code == 303
    conn = db(client)
    assert conn.execute("SELECT status FROM orders WHERE number=1051").fetchone()[0] == "refunded"
    assert conn.execute("SELECT COUNT(*) FROM refunds").fetchone()[0] == 1
    assert client.post("/admin/orders/1051/refund").status_code == 422  # cannot refund twice


def test_review_pagination_and_newsletter(client):
    assert "Page 1 of 3" in client.get("/products/CLO-TRP-01").text
    assert "Page 3 of 3" in client.get("/products/CLO-TRP-01?reviews_page=3").text
    client.post("/newsletter", data={"email": "New.Reader@Example.test"})
    row = db(client).execute("SELECT active FROM newsletter_subscribers WHERE email='new.reader@example.test'").fetchone()
    assert row["active"] == 1


def test_episodes_are_isolated(data_dir):
    first, second = create_episode(data_dir, 7), create_episode(data_dir, 7)
    app = make_app(data_dir)
    for ep in (first, second):
        c = TestClient(app, follow_redirects=False)
        c.cookies.set("sg_episode", ep.token)
        c.cookies.set("sg_session", ep.session_token)
        if ep is first:
            c.post("/cart/add", data={"sku": "BOK-ATL-01", "qty": "1"})
    count = lambda ep: connect(ep.db).execute("SELECT COUNT(*) FROM cart_items").fetchone()[0]
    assert count(first) == 1 and count(second) == 0


def test_admin_order_list_and_filter_render(client):
    login(client, "admin@shop.test")
    assert client.get("/admin").status_code == 200
    assert "#1042" in client.get("/admin/orders").text
    filtered = client.get("/admin/orders?status=shipped")
    assert filtered.status_code == 200 and "#1044" in filtered.text and "#1042" not in filtered.text
