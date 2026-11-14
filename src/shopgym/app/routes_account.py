"""Customer account: login, registration, profile, newsletter preference, addresses, orders."""

from datetime import datetime

from starlette.routing import Route

from shopgym.app.db import hash_password, verify_password
from shopgym.app.validation import validate_address, validate_email
from shopgym.app.web import page, redirect, render, require_user
from shopgym.config import SHOP_NOW

NOW = datetime.fromisoformat(SHOP_NOW).isoformat()
CANCELLABLE = ("processing", "placed")
ADDRESS_EDITABLE = ("processing", "placed")


@page
async def login_form(request):
    return render(request, "login.html", errors={}, email="")


@page
async def login_post(request):
    conn = request.state.conn
    form = await request.form()
    email = str(form.get("email", "")).strip().lower()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if user is None or not verify_password(str(form.get("password", "")), user["password_hash"]):
        return render(request, "login.html", status=422, errors={"password": "Email or password is wrong."},
                      email=email)
    conn.execute("UPDATE sessions SET user_id = ? WHERE token = ?", (user["id"], request.state.session_token))
    return redirect("/account", notice=f"Welcome back, {user['name']}")


@page
async def register_form(request):
    return render(request, "register.html", errors={}, form={})


@page
async def register_post(request):
    conn = request.state.conn
    form = await request.form()
    email = str(form.get("email", "")).strip().lower()
    errors = {}
    if error := validate_email(email):
        errors["email"] = error
    elif conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
        errors["email"] = "An account with this email already exists."
    if not str(form.get("name", "")).strip():
        errors["name"] = "Required."
    if len(str(form.get("password", ""))) < 8:
        errors["password"] = "Use at least 8 characters."
    elif form.get("password") != form.get("confirm"):
        errors["confirm"] = "Passwords do not match."
    if errors:
        return render(request, "register.html", status=422, errors=errors,
                      form={"email": email, "name": form.get("name", "")})
    cur = conn.execute("INSERT INTO users(email, name, password_hash, created_at) VALUES (?,?,?,?)",
                       (email, form["name"].strip(), hash_password(form["password"]), NOW))
    conn.execute("UPDATE sessions SET user_id = ? WHERE token = ?", (cur.lastrowid, request.state.session_token))
    return redirect("/account", notice="Your account is ready")


@page
async def logout(request):
    request.state.conn.execute("UPDATE sessions SET user_id = NULL WHERE token = ?", (request.state.session_token,))
    return redirect("/", notice="You are logged out")


@page
async def account_home(request):
    if (gate := require_user(request)) is not None:
        return gate
    conn, user = request.state.conn, request.state.user
    orders = conn.execute("SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC, number DESC LIMIT 3",
                          (user["id"],)).fetchall()
    subscribed = conn.execute("SELECT active FROM newsletter_subscribers WHERE email = ?",
                              (user["email"],)).fetchone()
    return render(request, "account.html", orders=orders, subscribed=bool(subscribed and subscribed["active"]))


@page
async def newsletter_pref(request):
    if (gate := require_user(request)) is not None:
        return gate
    form = await request.form()
    on = form.get("subscribed") == "1"
    request.state.conn.execute(
        "INSERT INTO newsletter_subscribers(email, active, created_at) VALUES (?, ?, ?)"
        " ON CONFLICT(email) DO UPDATE SET active = excluded.active",
        (request.state.user["email"], int(on), NOW))
    return redirect("/account", notice="Newsletter preference saved" if on else "You have unsubscribed")


@page
async def profile(request):
    if (gate := require_user(request)) is not None:
        return gate
    user = request.state.user
    return render(request, "profile.html", errors={}, form={"name": user["name"], "email": user["email"]})


@page
async def profile_post(request):
    if (gate := require_user(request)) is not None:
        return gate
    conn, user = request.state.conn, request.state.user
    form = await request.form()
    name = str(form.get("name", "")).strip()
    email = str(form.get("email", "")).strip().lower()
    errors = {"name": "Required."} if not name else {}
    if error := validate_email(email):
        errors["email"] = error
    elif conn.execute("SELECT 1 FROM users WHERE email = ? AND id != ?", (email, user["id"])).fetchone():
        errors["email"] = "Another account already uses this email."
    if errors:
        return render(request, "profile.html", status=422, errors=errors, form={"name": name, "email": email})
    conn.execute("UPDATE users SET name = ?, email = ? WHERE id = ?", (name, email, user["id"]))
    return redirect("/account/profile", notice="Profile saved")


def _addresses(conn, user_id: int) -> list:
    return conn.execute("SELECT * FROM addresses WHERE user_id = ? ORDER BY id", (user_id,)).fetchall()


@page
async def addresses(request):
    if (gate := require_user(request)) is not None:
        return gate
    return render(request, "addresses.html", addresses=_addresses(request.state.conn, request.state.user["id"]),
                  errors={}, form={"country": "United Kingdom"})


@page
async def address_add(request):
    if (gate := require_user(request)) is not None:
        return gate
    conn, user = request.state.conn, request.state.user
    form = await request.form()
    errors = validate_address(form)
    label = str(form.get("label", "")).strip() or "Address"
    if errors:
        return render(request, "addresses.html", status=422,
                      addresses=_addresses(conn, user["id"]), errors=errors, form=dict(form))
    make_default = form.get("is_default") == "1" or not _addresses(conn, user["id"])
    if make_default:
        conn.execute("UPDATE addresses SET is_default = 0 WHERE user_id = ?", (user["id"],))
    conn.execute(
        "INSERT INTO addresses(user_id, label, full_name, line1, city, postcode, country, is_default)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (user["id"], label, form["full_name"].strip(), form["line1"].strip(), form["city"].strip(),
         form["postcode"].strip(), form["country"], int(make_default)))
    return redirect("/account/addresses", notice="Address saved")


def _owned_address(conn, user_id: int, address_id: int):
    return conn.execute("SELECT * FROM addresses WHERE id = ? AND user_id = ?", (address_id, user_id)).fetchone()


@page
async def address_default(request):
    if (gate := require_user(request)) is not None:
        return gate
    conn, user = request.state.conn, request.state.user
    address = _owned_address(conn, user["id"], int(request.path_params["address_id"]))
    if address is None:
        return render(request, "not_found.html", status=404)
    conn.execute("UPDATE addresses SET is_default = CASE WHEN id = ? THEN 1 ELSE 0 END WHERE user_id = ?",
                 (address["id"], user["id"]))
    return redirect("/account/addresses", notice="Default address updated")


@page
async def address_delete(request):
    if (gate := require_user(request)) is not None:
        return gate
    conn, user = request.state.conn, request.state.user
    address = _owned_address(conn, user["id"], int(request.path_params["address_id"]))
    if address is None:
        return render(request, "not_found.html", status=404)
    conn.execute("DELETE FROM addresses WHERE id = ?", (address["id"],))
    return redirect("/account/addresses", notice="Address deleted")


@page
async def orders(request):
    if (gate := require_user(request)) is not None:
        return gate
    rows = request.state.conn.execute(
        "SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC, number DESC", (request.state.user["id"],)
    ).fetchall()
    return render(request, "orders.html", orders=rows)


def _owned_order(request):
    return request.state.conn.execute(
        "SELECT * FROM orders WHERE number = ? AND user_id = ?",
        (int(request.path_params["number"]), request.state.user["id"])).fetchone()


def _order_view(request, order, errors: dict | None = None, status: int = 200):
    conn = request.state.conn
    items = conn.execute("SELECT * FROM order_items WHERE order_id = ? ORDER BY id", (order["id"],)).fetchall()
    return render(request, "order.html", status=status, order=order, items=items, errors=errors or {},
                  events=conn.execute("SELECT * FROM order_events WHERE order_id = ? ORDER BY id",
                                      (order["id"],)).fetchall())


@page
async def order_detail(request):
    if (gate := require_user(request)) is not None:
        return gate
    order = _owned_order(request)
    if order is None:
        return render(request, "not_found.html", status=404)
    return _order_view(request, order)


def _event(conn, order_id: int, message: str) -> None:
    conn.execute("INSERT INTO order_events(order_id, created_at, message) VALUES (?,?,?)", (order_id, NOW, message))


@page
async def order_cancel(request):
    if (gate := require_user(request)) is not None:
        return gate
    conn = request.state.conn
    order = _owned_order(request)
    if order is None:
        return render(request, "not_found.html", status=404)
    if order["status"] not in CANCELLABLE:
        return redirect(f"/account/orders/{order['number']}", notice=f"Order is {order['status']} and cannot be cancelled")
    conn.execute("UPDATE orders SET status = 'cancelled' WHERE id = ?", (order["id"],))
    _event(conn, order["id"], "Cancelled by customer")
    return redirect(f"/account/orders/{order['number']}", notice=f"Order #{order['number']} cancelled")


@page
async def order_address(request):
    if (gate := require_user(request)) is not None:
        return gate
    conn = request.state.conn
    order = _owned_order(request)
    if order is None:
        return render(request, "not_found.html", status=404)
    if order["status"] not in ADDRESS_EDITABLE:
        return redirect(f"/account/orders/{order['number']}", notice="Shipping address can no longer be changed")
    form = await request.form()
    errors = validate_address(form)
    if errors:
        return _order_view(request, order, errors=errors, status=422)
    conn.execute(
        "UPDATE orders SET ship_name = ?, ship_line1 = ?, ship_city = ?, ship_postcode = ?, ship_country = ?"
        " WHERE id = ?", (form["full_name"].strip(), form["line1"].strip(), form["city"].strip(),
                          form["postcode"].strip(), form["country"], order["id"]))
    _event(conn, order["id"], "Shipping address changed by customer")
    return redirect(f"/account/orders/{order['number']}", notice="Shipping address updated")


def routes():
    return [
        Route("/login", login_form),
        Route("/login", login_post, methods=["POST"]),
        Route("/register", register_form),
        Route("/register", register_post, methods=["POST"]),
        Route("/logout", logout, methods=["POST"]),
        Route("/account", account_home),
        Route("/account/newsletter", newsletter_pref, methods=["POST"]),
        Route("/account/profile", profile),
        Route("/account/profile", profile_post, methods=["POST"]),
        Route("/account/addresses", addresses),
        Route("/account/addresses", address_add, methods=["POST"]),
        Route("/account/addresses/{address_id:int}/default", address_default, methods=["POST"]),
        Route("/account/addresses/{address_id:int}/delete", address_delete, methods=["POST"]),
        Route("/account/orders", orders),
        Route("/account/orders/{number:int}", order_detail),
        Route("/account/orders/{number:int}/cancel", order_cancel, methods=["POST"]),
        Route("/account/orders/{number:int}/address", order_address, methods=["POST"]),
    ]
