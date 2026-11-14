"""Scripted oracles for storefront tasks: search, catalogue, cart, checkout, reviews."""

import re

from shopgym.agents.oracle import Controller

COUNT_FOUND = re.compile(r"(\d+) found")
BEST = re.compile(r"\bbest\b", re.IGNORECASE)


def _search(c: Controller, text: str):
    yield c.fill("Search products", text, submit=True)


def _add_to_cart(c: Controller, qty: int):
    if qty != 1:
        yield c.choose("Quantity", str(qty))
    yield c.click("button", "Add to cart")


def _checkout_as_guest(c: Controller, coupon: str | None = None):
    """Cart -> shipping -> payment -> review -> place, filling the values the task gave."""
    p = c.params
    yield c.click("link", "Cart")
    yield c.click("link", "Go to checkout")
    yield c.fill("Email for order updates", p["email"])
    yield c.fill("Full name", p["full_name"])
    yield c.fill("Street address", p["line1"])
    yield c.fill("City", p["city"])
    yield c.fill("Postcode", p["postcode"])
    yield c.click("button", "Continue to payment")
    yield c.fill("Card number", "4242 4242 4242 4242")
    yield c.fill("Expiry", "12/30")
    yield c.fill("Security code", "123")
    if coupon:
        yield c.fill("Coupon code", coupon)
    yield c.click("button", "Review order")
    yield c.click("button", "Place order")


def newsletter_subscribe(c: Controller):
    yield c.fill("Email address", c.params["email"])
    yield c.click("button", "Subscribe")
    yield c.finish()


def search_count(c: Controller):
    yield from _search(c, c.params["query"])
    match = COUNT_FOUND.search(c.obs.text)
    yield c.finish(match.group(1))


def product_price(c: Controller):
    yield from _search(c, "Field Notes Atlas")
    yield c.click("link", "Field Notes Atlas")
    price = re.search(r"\$\d+\.\d{2}", c.obs.text).group(0)
    yield c.finish(price)


def cheapest_in_stock(c: Controller):
    yield c.choose("Department", "Electronics")
    yield c.check("In stock only")
    yield c.choose("Sort by", "Price, low to high")
    yield c.click("button", "Apply filters")
    yield c.finish(c.product_links()[0].name)


def cart_add_trail_runner(c: Controller):
    yield from _search(c, "Trail Runner Pro")
    yield c.click("link", "Trail Runner Pro")
    yield from _add_to_cart(c, c.params["lines"]["CLO-TRP-01"])
    yield c.finish()


def guest_checkout(c: Controller):
    yield from _search(c, "Ceramic Pour-Over Set")
    yield c.click("link", "Ceramic Pour-Over Set")
    yield from _add_to_cart(c, c.params["qty"])
    yield from _checkout_as_guest(c)
    yield c.finish()


def guest_checkout_coupon(c: Controller):
    yield from _search(c, "Field Notes Atlas")
    yield c.click("link", "Field Notes Atlas")
    yield from _add_to_cart(c, c.params["qty"])
    yield from _checkout_as_guest(c, coupon=c.params["coupon"])
    yield c.finish()


def cheapest_garden_add_two(c: Controller):
    yield c.choose("Department", "Garden")
    yield c.check("In stock only")
    yield c.choose("Sort by", "Price, low to high")
    yield c.click("button", "Apply filters")
    yield c.click("link", c.product_links()[0].name)
    yield from _add_to_cart(c, c.params["qty"])
    yield c.finish()


def last_product_sku(c: Controller):
    for _ in range(10):
        if c.obs.find("link", "Next page") is None:
            break
        yield c.click("link", "Next page")
    yield c.finish(c.product_links()[-1].href.rsplit("/", 1)[-1])


def home_filter_count(c: Controller):
    yield c.choose("Department", "Home")
    yield c.fill("Highest price (dollars)", "100")
    yield c.choose("Minimum rating", "3 stars")
    yield c.click("button", "Apply filters")
    yield c.finish(COUNT_FOUND.search(c.obs.text).group(1))


def trail_runner_best_reviews(c: Controller):
    total = 0
    while True:
        total += sum(1 for line in c.obs.text.splitlines() if BEST.search(line) and not line.startswith("#"))
        if c.obs.find("link", "Next page") is None:
            break
        yield c.click("link", "Next page")
    yield c.finish(str(total))


def write_review(c: Controller):
    yield c.choose("Rating", "4 of 5")
    yield c.fill("Title", "Bright and quiet")
    yield c.fill("Review", "The lamp is bright and quiet to use.")
    yield c.click("button", "Post review")
    yield c.finish()


SHOP_ORACLES = {
    "newsletter-subscribe": newsletter_subscribe,
    "search-count": search_count,
    "product-price": product_price,
    "cheapest-electronics": cheapest_in_stock,
    "add-to-cart": cart_add_trail_runner,
    "guest-checkout": guest_checkout,
    "guest-checkout-coupon": guest_checkout_coupon,
    "cheapest-garden-add-two": cheapest_garden_add_two,
    "last-product-sku": last_product_sku,
    "home-filter-count": home_filter_count,
    "trail-runner-best-reviews": trail_runner_best_reviews,
    "write-review": write_review,
}
