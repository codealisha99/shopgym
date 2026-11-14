"""Admin panel: dashboard, order management, products, review moderation, newsletter."""

from datetime import datetime

from starlette.routing import Route

from shopgym.app.web import page, redirect, render, require_admin
from shopgym.config import SHOP_NOW

NOW = datetime.fromisoformat(SHOP_NOW).isoformat()
SHIPPABLE = ("processing",)
REFUNDABLE = ("processing", "shipped", "delivered")


def _order(conn, number: int):
    return conn.execute("SELECT o.*, u.name AS customer_name FROM orders o LEFT JOIN users u ON u.id = o.user_id"
                        " WHERE o.number = ?", (number,)).fetchone()


def _log(conn, order_id: int, message: str) -> None:
    conn.execute("INSERT INTO order_events(order_id, created_at, message) VALUES (?,?,?)", (order_id, NOW, message))


@page
async def dashboard(request):
    if (gate := require_admin(request)) is not None:
        return gate
    conn = request.state.conn
    by_status = conn.execute("SELECT status, COUNT(*) AS n FROM orders GROUP BY status ORDER BY status").fetchall()
    stats = {
        "subscribers": conn.execute("SELECT COUNT(*) FROM newsletter_subscribers WHERE active = 1").fetchone()[0],
        "low_stock": conn.execute("SELECT COUNT(*) FROM products WHERE stock < 5 AND active = 1").fetchone()[0],
        "hidden_reviews": conn.execute("SELECT COUNT(*) FROM reviews WHERE hidden = 1").fetchone()[0],
    }
    recent = conn.execute("SELECT * FROM orders ORDER BY created_at DESC, number DESC LIMIT 6").fetchall()
    return render(request, "admin/dashboard.html", by_status=by_status, stats=stats, recent=recent, section="dashboard")


@page
async def orders_list(request):
    if (gate := require_admin(request)) is not None:
        return gate
    status = request.query_params.get("status", "")
    rows = request.state.conn.execute(
        "SELECT o.*, u.name AS customer_name FROM orders o LEFT JOIN users u ON u.id = o.user_id"
        " WHERE (? = '' OR o.status = ?) ORDER BY o.number DESC", (status, status)).fetchall()
    return render(request, "admin/orders.html", orders=rows, status_filter=status, section="orders")


def _order_page(request, order, errors: dict | None = None, status: int = 200):
    conn = request.state.conn
    return render(request, "admin/order.html", status=status, order=order, errors=errors or {}, section="orders",
                  items=conn.execute("SELECT * FROM order_items WHERE order_id = ? ORDER BY id", (order["id"],)).fetchall(),
                  events=conn.execute("SELECT * FROM order_events WHERE order_id = ? ORDER BY id", (order["id"],)).fetchall(),
                  refunds=conn.execute("SELECT * FROM refunds WHERE order_id = ?", (order["id"],)).fetchall())


@page
async def order_detail(request):
    if (gate := require_admin(request)) is not None:
        return gate
    order = _order(request.state.conn, int(request.path_params["number"]))
    if order is None:
        return render(request, "not_found.html", status=404)
    return _order_page(request, order)


@page
async def order_ship(request):
    if (gate := require_admin(request)) is not None:
        return gate
    conn = request.state.conn
    order = _order(conn, int(request.path_params["number"]))
    if order is None:
        return render(request, "not_found.html", status=404)
    form = await request.form()
    tracking = str(form.get("tracking", "")).strip().upper()
    if order["status"] not in SHIPPABLE:
        return _order_page(request, order, errors={"status": f"Order is {order['status']}; only processing orders ship."}, status=422)
    if len(tracking) < 6:
        return _order_page(request, order, errors={"tracking": "Enter the carrier tracking number."}, status=422)
    conn.execute("UPDATE orders SET status = 'shipped', tracking_number = ? WHERE id = ?", (tracking, order["id"]))
    _log(conn, order["id"], f"Marked shipped, tracking {tracking}")
    return redirect(f"/admin/orders/{order['number']}", notice="Order marked as shipped")


@page
async def order_refund(request):
    if (gate := require_admin(request)) is not None:
        return gate
    conn = request.state.conn
    order = _order(conn, int(request.path_params["number"]))
    if order is None:
        return render(request, "not_found.html", status=404)
    if order["status"] not in REFUNDABLE:
        return _order_page(request, order, errors={"status": f"Order is {order['status']} and cannot be refunded."}, status=422)
    conn.execute("UPDATE orders SET status = 'refunded' WHERE id = ?", (order["id"],))
    conn.execute("INSERT INTO refunds(order_id, amount_cents, created_at) VALUES (?,?,?)",
                 (order["id"], order["total_cents"], NOW))
    _log(conn, order["id"], f"Refunded {order['total_cents']} cents")
    return redirect(f"/admin/orders/{order['number']}", notice=f"Order #{order['number']} refunded")


@page
async def products_list(request):
    if (gate := require_admin(request)) is not None:
        return gate
    q = request.query_params.get("q", "")
    rows = request.state.conn.execute(
        "SELECT p.*, c.name AS category_name FROM products p JOIN categories c ON c.id = p.category_id"
        " WHERE p.name LIKE ? OR p.sku LIKE ? ORDER BY p.sku", (f"%{q}%", f"%{q}%")).fetchall()
    return render(request, "admin/products.html", products=rows, q=q, section="products")


@page
async def product_edit(request):
    if (gate := require_admin(request)) is not None:
        return gate
    product = request.state.conn.execute("SELECT p.*, c.name AS category_name FROM products p"
                                         " JOIN categories c ON c.id = p.category_id WHERE p.sku = ?",
                                         (request.path_params["sku"],)).fetchone()
    if product is None:
        return render(request, "not_found.html", status=404)
    return render(request, "admin/product.html", product=product, errors={}, section="products")


@page
async def product_save(request):
    if (gate := require_admin(request)) is not None:
        return gate
    conn = request.state.conn
    product = conn.execute("SELECT * FROM products WHERE sku = ?", (request.path_params["sku"],)).fetchone()
    if product is None:
        return render(request, "not_found.html", status=404)
    form = await request.form()
    errors = {}
    try:
        price_cents = round(float(form.get("price", "")) * 100)
        if price_cents <= 0:
            raise ValueError
    except ValueError:
        errors["price"] = "Enter a price above zero."
    try:
        stock = int(form.get("stock", ""))
        if stock < 0:
            raise ValueError
    except ValueError:
        errors["stock"] = "Stock must be zero or more."
    if errors:
        return render(request, "admin/product.html", status=422, product=product, errors=errors, section="products")
    conn.execute("UPDATE products SET price_cents = ?, stock = ? WHERE id = ?", (price_cents, stock, product["id"]))
    return redirect(f"/admin/products/{product['sku']}", notice="Product saved")


@page
async def reviews_list(request):
    if (gate := require_admin(request)) is not None:
        return gate
    rows = request.state.conn.execute(
        "SELECT r.*, p.sku, p.name AS product_name, u.email AS author_email FROM reviews r"
        " JOIN products p ON p.id = r.product_id JOIN users u ON u.id = r.user_id ORDER BY r.id").fetchall()
    return render(request, "admin/reviews.html", reviews=rows, section="reviews")


@page
async def review_hide(request):
    if (gate := require_admin(request)) is not None:
        return gate
    request.state.conn.execute("UPDATE reviews SET hidden = 1 WHERE id = ?", (int(request.path_params["review_id"]),))
    return redirect("/admin/reviews", notice="Review hidden from the storefront")


@page
async def newsletter_list(request):
    if (gate := require_admin(request)) is not None:
        return gate
    rows = request.state.conn.execute("SELECT * FROM newsletter_subscribers ORDER BY email").fetchall()
    return render(request, "admin/newsletter.html", subscribers=rows, section="newsletter")


def routes():
    return [
        Route("/admin", dashboard),
        Route("/admin/orders", orders_list),
        Route("/admin/orders/{number:int}", order_detail),
        Route("/admin/orders/{number:int}/ship", order_ship, methods=["POST"]),
        Route("/admin/orders/{number:int}/refund", order_refund, methods=["POST"]),
        Route("/admin/products", products_list),
        Route("/admin/products/{sku}", product_edit),
        Route("/admin/products/{sku}", product_save, methods=["POST"]),
        Route("/admin/reviews", reviews_list),
        Route("/admin/reviews/{review_id:int}/hide", review_hide, methods=["POST"]),
        Route("/admin/newsletter", newsletter_list),
    ]
