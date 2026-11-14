"""Public deployment: per-visitor copies, capacity cap, expiry, body and write limits."""

import os
import sqlite3

import pytest
from starlette.testclient import TestClient

from shopgym.app.limits import RateLimiter
from shopgym.app.live import LiveRegistry
from shopgym.app.server import make_app
from shopgym.config import EPISODE_COOKIE


class Clock:
    def __init__(self, now: float = 1_000_000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now


@pytest.fixture()
def live_app(data_dir):
    return make_app(data_dir, live=True)


def _count(db, sql, args=()):
    conn = sqlite3.connect(db)
    try:
        return conn.execute(sql, args).fetchone()[0]
    finally:
        conn.close()


def _db_for(client, data_dir):
    token = client.cookies.get(EPISODE_COOKIE)
    return data_dir / "episodes" / token / "shop.db"


def test_first_visit_gets_its_own_copy_and_cookie(live_app, data_dir):
    client = TestClient(live_app, follow_redirects=False)
    assert client.get("/").status_code == 200
    assert client.cookies.get(EPISODE_COOKIE)
    assert "ShopGym evaluation target: fake store, data resets" in client.get("/").text
    assert not (data_dir / "default" / "shop.db").exists()


def test_visitors_cannot_see_each_others_cart_or_admin_edits(live_app, data_dir):
    a = TestClient(live_app, follow_redirects=False)
    b = TestClient(live_app, follow_redirects=False)
    a.get("/")
    b.get("/")
    assert a.cookies.get(EPISODE_COOKIE) != b.cookies.get(EPISODE_COOKIE)
    a.post("/cart/add", data={"sku": "CLO-TRP-01", "qty": "2"})
    assert _count(_db_for(a, data_dir), "SELECT COUNT(*) FROM cart_items") == 1
    assert _count(_db_for(b, data_dir), "SELECT COUNT(*) FROM cart_items") == 0


def test_request_with_unknown_episode_cookie_gets_a_fresh_copy(live_app, data_dir):
    client = TestClient(live_app, follow_redirects=False)
    response = client.get("/", headers={"cookie": "sg_episode=" + "0" * 32})
    assert response.status_code == 200
    issued = response.cookies.get(EPISODE_COOKIE)
    assert issued and issued != "0" * 32
    assert (data_dir / "episodes" / issued / "shop.db").exists()


def test_capacity_cap_returns_503_instead_of_evicting(live_app):
    live_app.state.live.max_copies = 1
    first = TestClient(live_app, follow_redirects=False)
    assert first.get("/").status_code == 200
    second = TestClient(live_app, follow_redirects=False)
    response = second.get("/")
    assert response.status_code == 503 and "full" in response.text
    assert first.get("/cart").status_code == 200


def test_idle_copies_expire_and_active_ones_stay(data_dir):
    clock = Clock()
    registry = LiveRegistry(data_dir, max_copies=10, idle_seconds=60, new_per_hour_per_ip=100, clock=clock)
    old = registry.create("1.1.1.1")
    fresh = registry.create("2.2.2.2")
    # Directory mtimes are real wall-clock times; pin them to the fake clock.
    os.utime(data_dir / "episodes" / old, (clock.now, clock.now))
    os.utime(data_dir / "episodes" / fresh, (clock.now + 30, clock.now + 30))
    clock.now += 75  # old is 75s idle, fresh is 45s idle
    assert registry.sweep() == 1
    assert registry.touch(old) is None
    assert registry.touch(fresh) is not None


def test_new_copies_per_ip_are_rate_limited(data_dir):
    registry = LiveRegistry(data_dir, max_copies=10, idle_seconds=60, new_per_hour_per_ip=2)
    assert registry.create("3.3.3.3") and registry.create("3.3.3.3")
    assert registry.create("3.3.3.3") is None
    assert registry.create("4.4.4.4") is not None


def test_oversized_body_is_rejected(live_app):
    client = TestClient(live_app, follow_redirects=False)
    client.get("/")
    big = {"email": "x" * 40_000}
    response = client.post("/newsletter", data=big)
    assert response.status_code == 413


def test_write_rate_limit_returns_429(live_app):
    client = TestClient(live_app, follow_redirects=False)
    client.get("/")
    statuses = [client.post("/newsletter", data={"email": "a@example.test"}).status_code for _ in range(70)]
    assert 429 in statuses and statuses.index(429) >= 59


def test_rate_limiter_window_slides():
    clock = Clock(0.0)
    limiter = RateLimiter(2, 10.0, clock=clock)
    assert limiter.allow("k") and limiter.allow("k") and not limiter.allow("k")
    clock.now = 10.0
    assert limiter.allow("k")
