"""Scripted oracles for account and admin tasks."""

import re

from shopgym.agents.oracle import Controller
from shopgym.env.actions import Action

LOGIN_AS_ADMIN_EMAIL = "admin@shop.test"


def _log_in(c: Controller, email: str, password: str = "password123"):
    yield c.fill("Email", email)
    yield c.fill("Password", password)
    yield c.click("button", "Log in")


def _admin_home(c: Controller):
    yield from _log_in(c, LOGIN_AS_ADMIN_EMAIL)
    yield c.click("link", "Admin")


def _admin_orders(c: Controller):
    yield from _admin_home(c)
    yield c.click("link", "Orders")


def _shipping_fields(c: Controller):
    p = c.params
    yield c.fill("Full name", p["full_name"])
    yield c.fill("Street address", p["line1"])
    yield c.fill("City", p["city"])
    yield c.fill("Postcode", p["postcode"])


def order_status_after_login(c: Controller):
    yield from _log_in(c, c.params.get("email", "grace@shop.test"))
    yield c.goto("/account/orders/1051")
    status = re.search(r"Status: .*?\n(\w+)", c.obs.text)
    word = status.group(1) if status else c.db.execute("SELECT status FROM orders WHERE number = 1051").fetchone()[0]
    yield c.finish(word)


def register_account(c: Controller):
    p = c.params
    yield c.fill("Full name", p["name"])
    yield c.fill("Email", p["email"])
    yield c.fill("Password (at least 8", p["password"])
    yield c.fill("Confirm password", p["password"])
    yield c.click("button", "Create account")
    yield c.finish()


def update_profile_name(c: Controller):
    yield c.fill("Name", c.params["name"])
    yield c.click("button", "Save profile")
    yield c.finish()


def newsletter_unsubscribe(c: Controller):
    yield c.click("checkbox", "Send me the monthly newsletter")
    yield c.click("button", "Save preference")
    yield c.finish()


def remove_cart_line(c: Controller):
    yield c.click("button", "Remove")  # first line is Canvas Tote (sorted by name)
    yield c.click("button", "Remove item")
    yield c.finish()


def cancel_order_1042(c: Controller):
    yield c.click("link", "#1042")
    yield c.click("button", "Cancel this order")
    yield c.click("button", "Cancel order")
    yield c.finish()


def change_recent_address(c: Controller):
    yield c.click("link", "#1043")
    yield from _shipping_fields(c)
    yield c.click("button", "Save address")
    yield c.finish()


def add_default_address(c: Controller):
    p = c.params
    yield c.fill("Label", p["label"])
    yield c.fill("Full name", p["full_name"])
    yield c.fill("Street address", p["line1"])
    yield c.fill("City", p["city"])
    yield c.fill("Postcode", p["postcode"])
    yield c.check("Use as my default address")
    yield c.click("button", "Save address")
    yield c.finish()


def cancel_shipped_refusal(c: Controller):
    yield c.click("link", "#1044")
    yield c.finish("not cancellable")


def admin_refund_order(c: Controller):
    yield from _admin_orders(c)
    yield c.click("link", f"#{c.params['number']}")
    yield c.click("button", "Refund order")
    yield c.click("button", "Issue refund")
    yield c.finish()


def admin_set_stock(c: Controller):
    yield from _admin_home(c)
    yield c.click("link", "Products")
    yield c.fill("Name or SKU", c.params["sku"], submit=True)
    yield c.click("link", "Edit")
    yield c.fill("Units in stock", str(c.params["stock"]))
    yield c.click("button", "Save product")
    yield c.finish()


def admin_mark_shipped(c: Controller):
    yield from _admin_orders(c)
    yield c.click("link", f"#{c.params['number']}")
    yield c.fill("Carrier tracking number", c.params["tracking"])
    yield c.click("button", "Mark as shipped")
    yield c.finish()


def admin_hide_bad_review(c: Controller):
    yield from _admin_home(c)
    yield c.click("link", "Reviews")
    # The setup-seeded review is the newest row, so it is the last visible Hide button.
    hides = [e for e in c.obs.elements if e.role == "button" and e.name == "Hide"]
    yield Action(type="click", element=hides[-1].id)
    yield c.finish()


def admin_subscriber_count(c: Controller):
    yield from _admin_home(c)
    yield c.click("link", "Newsletter")
    count = sum(1 for line in c.obs.text.splitlines() if line == "Active")
    yield c.finish(str(count))


ACCOUNT_ORACLES = {
    "order-status-after-login": order_status_after_login,
    "register-account": register_account,
    "update-profile-name": update_profile_name,
    "newsletter-unsubscribe": newsletter_unsubscribe,
    "remove-cart-line": remove_cart_line,
    "cancel-order-1042": cancel_order_1042,
    "change-recent-address": change_recent_address,
    "add-default-address": add_default_address,
    "cancel-shipped-refusal": cancel_shipped_refusal,
    "admin-refund-order": admin_refund_order,
    "admin-refund-disambiguated": admin_refund_order,
    "admin-set-stock": admin_set_stock,
    "admin-mark-shipped": admin_mark_shipped,
    "admin-hide-bad-review": admin_hide_bad_review,
    "admin-subscriber-count": admin_subscriber_count,
}
