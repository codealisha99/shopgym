"""Storefront: home, catalogue, product pages, reviews, cart and newsletter."""

from datetime import datetime
from urllib.parse import urlencode

from shopgym.app.catalog import paginate, parse_page, product_by_sku, search_products
from shopgym.app.validation import validate_email
from shopgym.app.web import page, redirect, render
from shopgym.config import PAGE_SIZE, REVIEW_PAGE_SIZE


def _float_or_none(raw: str | None) -> float | None:
    try:
        return float(raw) if raw not in (None, "") else None
    except ValueError:
        return None


@page
async def home(request):
    conn = request.state.conn
    featured = search_products(conn, sort="rating")[:4]
    departments = conn.execute("SELECT slug, name FROM categories ORDER BY name").fetchall()
    tiles = []
    for dept in departments:
        sample = search_products(conn, category=dept["slug"], sort="rating")
        tiles.append({"slug": dept["slug"], "name": dept["name"], "sample": sample[0]["name"] if sample else ""})
    return render(request, "home.html", featured=featured, tiles=tiles)


@page
async def products(request):
    conn = request.state.conn
    qp = request.query_params
    max_dollars = _float_or_none(qp.get("max_price"))
    rows = search_products(
        conn, q=qp.get("q", ""), category=qp.get("category", ""),
        max_price_cents=None if max_dollars is None else round(max_dollars * 100),
        min_rating=_float_or_none(qp.get("min_rating")),
        in_stock_only=qp.get("in_stock") == "1", sort=qp.get("sort", "name"))
    items, pages = paginate(rows, parse_page(qp.get("page")), PAGE_SIZE)
    kept = urlencode({k: v for k, v in qp.items() if k != "page" and v})
    names = {c["slug"]: c["name"] for c in conn.execute("SELECT slug, name FROM categories")}
    return render(request, "products.html", products=items, total=len(rows), pages=pages,
                  page_no=min(parse_page(qp.get("page")), pages), filters=dict(qp),
                  base_url=f"/products?{kept}&" if kept else "/products?",
                  heading=names.get(qp.get("category", ""), "All products"))


@page
async def product_detail(request):
    conn = request.state.conn
    product = product_by_sku(conn, request.path_params["sku"])
    if product is None:
        return render(request, "not_found.html", status=404)
    return _product_page(request, product, _reviews(conn, product["id"]), errors={}, form={})


def _reviews(conn, product_id: int) -> list:
    return conn.execute(
        "SELECT r.*, u.name AS author FROM reviews r JOIN users u ON u.id = r.user_id"
        " WHERE r.product_id = ? AND r.hidden = 0 ORDER BY r.created_at DESC, r.id DESC",
        (product_id,)).fetchall()


def _product_page(request, product, reviews, errors: dict, form: dict, status: int = 200):
    current = parse_page(request.query_params.get("reviews_page"))
    shown, pages = paginate(reviews, current, REVIEW_PAGE_SIZE)
    total = len(reviews)
    distribution = [{"stars": n, "count": sum(1 for r in reviews if r["rating"] == n)} for n in range(5, 0, -1)]
    for row in distribution:
        row["share"] = round(100 * row["count"] / total) if total else 0
    return render(request, "product.html", status=status, product=product, reviews=shown,
                  review_pages=pages, review_page=min(current, pages), errors=errors, form=form,
                  distribution=distribution, review_total=total)


@page
async def post_review(request):
    conn = request.state.conn
    user = request.state.user
    product = product_by_sku(conn, request.path_params["sku"])
    if product is None:
        return render(request, "not_found.html", status=404)
    if user is None:
        return redirect("/login?notice=Log+in+to+review+this+product")
    form = await request.form()
    errors = {}
    try:
        rating = int(form.get("rating", ""))
        if not 1 <= rating <= 5:
            raise ValueError
    except ValueError:
        errors["rating"] = "Choose a rating from 1 to 5."
    if not str(form.get("title", "")).strip():
        errors["title"] = "Give your review a title."
    if len(str(form.get("body", "")).strip()) < 10:
        errors["body"] = "Write at least 10 characters."
    if errors:
        return _product_page(request, product, _reviews(conn, product["id"]), errors, dict(form), status=422)
    conn.execute(
        "INSERT INTO reviews(product_id, user_id, rating, title, body, created_at) VALUES (?,?,?,?,?,?)",
        (product["id"], user["id"], rating, form["title"].strip(), form["body"].strip(),
         datetime(2026, 3, 15, 12).isoformat()))
    return redirect(f"/products/{product['sku']}", notice="Thanks, your review is posted")


@page
async def newsletter(request):
    conn = request.state.conn
    form = await request.form()
    email = str(form.get("email", "")).strip().lower()
    error = validate_email(email)
    if error:
        return redirect("/", notice=error)
    conn.execute(
        "INSERT INTO newsletter_subscribers(email, active, created_at) VALUES (?, 1, ?)"
        " ON CONFLICT(email) DO UPDATE SET active = 1",
        (email, datetime(2026, 3, 15, 12).isoformat()))
    return redirect("/", notice="You are subscribed to the newsletter")


@page
async def cart_view(request):
    conn = request.state.conn
    lines = conn.execute(
        "SELECT p.sku, p.name, p.price_cents, p.stock, c.qty, c.qty * p.price_cents AS line_cents"
        " FROM cart_items c JOIN products p ON p.id = c.product_id WHERE c.session_token = ?"
        " ORDER BY p.name", (request.state.session_token,)).fetchall()
    subtotal = sum(line["line_cents"] for line in lines)
    return render(request, "cart.html", lines=lines, subtotal=subtotal)


def _current_stock(conn, sku: str):
    return conn.execute("SELECT id, stock FROM products WHERE sku = ? AND active = 1", (sku,)).fetchone()


@page
async def cart_add(request):
    conn = request.state.conn
    form = await request.form()
    product = _current_stock(conn, str(form.get("sku", "")))
    if product is None:
        return redirect("/products", notice="That product is no longer available")
    try:
        qty = int(form.get("qty", "1"))
    except ValueError:
        qty = 0
    if qty < 1:
        return redirect(f"/products/{form['sku']}", notice="Quantity must be at least 1")
    token = request.state.session_token
    existing = conn.execute("SELECT qty FROM cart_items WHERE session_token = ? AND product_id = ?",
                            (token, product["id"])).fetchone()
    new_qty = qty + (existing["qty"] if existing else 0)
    if new_qty > product["stock"]:
        return redirect(f"/products/{form['sku']}", notice=f"Only {product['stock']} left in stock")
    conn.execute("INSERT INTO cart_items(session_token, product_id, qty) VALUES (?,?,?)"
                 " ON CONFLICT(session_token, product_id) DO UPDATE SET qty = excluded.qty",
                 (token, product["id"], new_qty))
    return redirect("/cart", notice=f"Added {qty} to your cart")


@page
async def cart_update(request):
    conn = request.state.conn
    form = await request.form()
    product = _current_stock(conn, str(form.get("sku", "")))
    token = request.state.session_token
    try:
        qty = int(form.get("qty", "0"))
    except ValueError:
        qty = -1
    if product is None or qty < 0 or qty > product["stock"]:
        return redirect("/cart", notice="Could not update that line")
    if qty == 0:
        conn.execute("DELETE FROM cart_items WHERE session_token = ? AND product_id = ?", (token, product["id"]))
    else:
        conn.execute("UPDATE cart_items SET qty = ? WHERE session_token = ? AND product_id = ?",
                     (qty, token, product["id"]))
    return redirect("/cart", notice="Cart updated")


@page
async def cart_remove(request):
    conn = request.state.conn
    form = await request.form()
    product = _current_stock(conn, str(form.get("sku", "")))
    if product is not None:
        conn.execute("DELETE FROM cart_items WHERE session_token = ? AND product_id = ?",
                     (request.state.session_token, product["id"]))
    return redirect("/cart", notice="Item removed")


def routes():
    from starlette.routing import Route
    return [
        Route("/", home),
        Route("/products", products),
        Route("/products/{sku}", product_detail),
        Route("/products/{sku}/reviews", post_review, methods=["POST"]),
        Route("/newsletter", newsletter, methods=["POST"]),
        Route("/cart", cart_view),
        Route("/cart/add", cart_add, methods=["POST"]),
        Route("/cart/update", cart_update, methods=["POST"]),
        Route("/cart/remove", cart_remove, methods=["POST"]),
    ]

