"""Starlette application factory. `shopgym serve` runs it with uvicorn."""

from pathlib import Path

from starlette.applications import Starlette
from starlette.responses import HTMLResponse
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles

from shopgym.app import routes_account, routes_admin, routes_checkout, routes_shop
from shopgym.app.limits import BodyLimit, RateLimiter, WriteRateLimit
from shopgym.app.live import LiveRegistry
from shopgym.app.web import templates
from shopgym.config import (LIVE_IDLE_MINUTES, LIVE_MAX_COPIES, LIVE_NEW_COPIES_PER_HOUR_PER_IP,
                            LIVE_WRITES_PER_MINUTE_PER_IP, MAX_BODY_BYTES)

STATIC_DIR = Path(__file__).parent / "static"


def make_app(data_dir: Path, live: bool = False) -> Starlette:
    app = Starlette(routes=[
        Mount("/static", StaticFiles(directory=STATIC_DIR), name="static"),
        *routes_shop.routes(),
        *routes_checkout.routes(),
        *routes_account.routes(),
        *routes_admin.routes(),
    ])
    app.state.data_dir = Path(data_dir)
    app.state.live = None
    if live:
        app.state.live = LiveRegistry(Path(data_dir), LIVE_MAX_COPIES, LIVE_IDLE_MINUTES * 60,
                                      LIVE_NEW_COPIES_PER_HOUR_PER_IP)
        app.add_middleware(WriteRateLimit, limiter=RateLimiter(LIVE_WRITES_PER_MINUTE_PER_IP, 60.0))
        app.add_middleware(BodyLimit, max_bytes=MAX_BODY_BYTES)

    async def not_found(request, exc):
        html = templates.get_template("not_found.html").render(request=request, user=None, cart_count=0,
                                                              categories=[], notice=None, path=request.url.path)
        return HTMLResponse(html, status_code=404)

    app.add_exception_handler(404, not_found)
    return app


def create_app() -> Starlette:
    """Factory used by `shopgym serve` (uvicorn --factory) and by the harness."""
    from shopgym.config import data_dir, live_mode
    return make_app(data_dir(), live=live_mode())
