"""Checkout: shipping -> payment -> review -> place order. Each step re-validates what came before."""

from datetime import datetime

from starlette.routing import Route

from shopgym.app.validation import validate_address, validate_card, validate_email
from shopgym.app.web import page, redirect, render
from shopgym.config import FREE_SHIPPING_THRESHOLD_CENTS, SHIPPING_CENTS, SHOP_NOW

SHIP_FIELDS = ("email", "full_name", "line1", "city", "postcode", "country")
TODAY = datetime.fromisoformat(SHOP_NOW).date()


def _cart_lines(conn, token: str) -> list:
    return conn.execute(
        "SELECT p.id AS product_id, p.sku, p.name, p.price_cents, p.stock, c.qty,"
        " c.qty * p.price_cents AS line_cents FROM cart_items c JOIN products p ON p.id = c.product_id"
        " WHERE c.session_token = ? ORDER BY p.name", (token,)).fetchall()


def _coupon_percent(conn, code: str) -> int | None:
    if not code:
        return None
    row = conn.execute("SELECT percent_off FROM coupons WHERE code = ? AND active = 1",
                       (code.strip().upper(),)).fetchone()
    return row["percent_off"] if row else None


def _totals(lines, percent: int | None) -> dict:
    subtotal = sum(line["line_cents"] for line in lines)
    discount = round(subtotal * percent / 100) if percent else 0
    shipping = 0 if subtotal >= FREE_SHIPPING_THRESHOLD_CENTS else SHIPPING_CENTS
    return {"subtotal": subtotal, "discount": discount, "shipping": shipping,
            "total": subtotal - discount + shipping}


def _ship_form(form) -> dict:
    return {k: str(form.get(k, "")).strip() for k in SHIP_FIELDS}


def _validate_ship(ship: dict, logged_in: bool) -> dict:
    errors = validate_address(ship)
    if not logged_in and (error := validate_email(ship["email"])):
        errors["email"] = error
    return errors


def _redirect_if_empty(request):
    if not _cart_lines(request.state.conn, request.state.session_token):
        return redirect("/cart", notice="Your cart is empty")
    return None


@page
async def checkout_start(request):
    if (early := _redirect_if_empty(request)) is not None:
        return early
    user = request.state.user
    conn = request.state.conn
    default = conn.execute("SELECT * FROM addresses WHERE user_id = ? AND is_default = 1",
                           (user["id"],)).fetchone() if user else None
    prefill = {"email": user["email"] if user else "", "full_name": default["full_name"] if default else "",
               "line1": default["line1"] if default else "", "city": default["city"] if default else "",
               "postcode": default["postcode"] if default else "", "country": default["country"] if default else "United Kingdom"}
    return render(request, "checkout_shipping.html", ship=prefill, errors={}, lines=_cart_lines(conn, request.state.session_token))


@page
async def checkout_shipping(request):
    if (early := _redirect_if_empty(request)) is not None:
        return early
    form = await request.form()
    ship = _ship_form(form)
    user = request.state.user
    if user:
        ship["email"] = user["email"]
    errors = _validate_ship(ship, user is not None)
    if errors:
        return render(request, "checkout_shipping.html", status=422, ship=ship, errors=errors,
                      lines=_cart_lines(request.state.conn, request.state.session_token))
    return render(request, "checkout_payment.html", ship=ship, errors={}, coupon="")


@page
async def checkout_payment(request):
    if (early := _redirect_if_empty(request)) is not None:
        return early
    form = await request.form()
    ship = _ship_form(form)
    coupon = str(form.get("coupon", "")).strip().upper()
    errors = _validate_ship(ship, request.state.user is not None)
    errors.update(validate_card(form, TODAY))
    if coupon and _coupon_percent(request.state.conn, coupon) is None:
        errors["coupon"] = "That coupon code is not valid."
    if errors:
        return render(request, "checkout_payment.html", status=422, ship=ship, errors=errors, coupon=coupon)
    return _review(request, ship, coupon, card_last4=str(form["card_number"]).replace(" ", "").replace("-", "")[-4:])


def _review(request, ship: dict, coupon: str, card_last4: str):
    conn = request.state.conn
    lines = _cart_lines(conn, request.state.session_token)
    percent = _coupon_percent(conn, coupon)
    return render(request, "checkout_review.html", ship=ship, coupon=coupon, lines=lines,
                  totals=_totals(lines, percent), card_last4=card_last4)


def _check_stock(lines) -> str | None:
    for line in lines:
        if line["qty"] > line["stock"]:
            return f"Only {line['stock']} of {line['name']} left"
    return None


@page
async def checkout_place(request):
    if (early := _redirect_if_empty(request)) is not None:
        return early
    conn = request.state.conn
    user = request.state.user
    form = await request.form()
    ship = _ship_form(form)
    coupon = str(form.get("coupon", "")).strip().upper()
    invalid_coupon = bool(coupon) and _coupon_percent(conn, coupon) is None
    if _validate_ship(ship, user is not None) or invalid_coupon:
        return redirect("/checkout", notice="Check your details and try again")
    lines = _cart_lines(conn, request.state.session_token)
    if problem := _check_stock(lines):
        return redirect("/cart", notice=problem)
    totals = _totals(lines, _coupon_percent(conn, coupon))
    number = conn.execute("SELECT COALESCE(MAX(number), 1000) + 1 FROM orders").fetchone()[0]
    now = datetime.fromisoformat(SHOP_NOW).isoformat()
    cur = conn.execute(
        "INSERT INTO orders(number, user_id, email, status, subtotal_cents, discount_cents, shipping_cents,"
        " total_cents, coupon, ship_name, ship_line1, ship_city, ship_postcode, ship_country, created_at)"
        " VALUES (?,?,?, 'processing', ?,?,?,?,?,?,?,?,?,?,?)",
        (number, user["id"] if user else None, ship["email"], totals["subtotal"], totals["discount"],
         totals["shipping"], totals["total"], coupon or None, ship["full_name"], ship["line1"],
         ship["city"], ship["postcode"], ship["country"], now))
    for line in lines:
        conn.execute("INSERT INTO order_items(order_id, product_id, product_name, unit_price_cents, qty)"
                     " VALUES (?,?,?,?,?)", (cur.lastrowid, line["product_id"], line["name"],
                                           line["price_cents"], line["qty"]))
        conn.execute("UPDATE products SET stock = stock - ? WHERE id = ?", (line["qty"], line["product_id"]))
    conn.execute("INSERT INTO order_events(order_id, created_at, message) VALUES (?,?,?)",
                 (cur.lastrowid, now, "Order placed"))
    conn.execute("DELETE FROM cart_items WHERE session_token = ?", (request.state.session_token,))
    return redirect(f"/checkout/complete/{number}")


@page
async def checkout_complete(request):
    order = request.state.conn.execute("SELECT * FROM orders WHERE number = ?",
                                       (int(request.path_params["number"]),)).fetchone()
    if order is None:
        return render(request, "not_found.html", status=404)
    return render(request, "checkout_done.html", order=order)


def routes():
    return [
        Route("/checkout", checkout_start),
        Route("/checkout/shipping", checkout_shipping, methods=["POST"]),
        Route("/checkout/payment", checkout_payment, methods=["POST"]),
        Route("/checkout/place", checkout_place, methods=["POST"]),
        Route("/checkout/complete/{number:int}", checkout_complete),
    ]

