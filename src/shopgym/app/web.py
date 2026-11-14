"""Request plumbing: episode-scoped databases, sessions, rendering and the page decorator.

Each browser carries an `sg_episode` cookie. The cookie picks which SQLite file the request
reads and writes, so parallel episodes never see each other's carts or orders. No cookie
means the shared demo database.
"""

import functools
import re
import secrets
from pathlib import Path

from starlette.responses import HTMLResponse, RedirectResponse, Response
from starlette.templating import Jinja2Templates

from shopgym.app.db import connect
from shopgym.app.seed import build_database
from shopgym.config import EPISODE_COOKIE, SEED_DEFAULT, SESSION_COOKIE

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
EPISODE_RE = re.compile(r"^[0-9a-f]{32}$")


def money(cents: int | None) -> str:
    return "" if cents is None else f"${cents / 100:,.2f}"


templates.env.filters["money"] = money


def episode_db_path(data_dir: Path, episode: str | None) -> Path:
    """Map an episode cookie to its database file. Only 32 hex chars are accepted (no path tricks)."""
    if episode and EPISODE_RE.match(episode):
        path = data_dir / "episodes" / episode / "shop.db"
        if path.exists():
            return path
    default = data_dir / "default" / "shop.db"
    if not default.exists():
        build_database(default, SEED_DEFAULT)
    return default


def _load_user(conn, token: str):
    return conn.execute(
        "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token = ?", (token,)
    ).fetchone()


def _ensure_session(conn, cookie: str | None) -> tuple[str, bool]:
    if cookie and conn.execute("SELECT 1 FROM sessions WHERE token = ?", (cookie,)).fetchone():
        return cookie, False
    token = secrets.token_hex(16)
    conn.execute("INSERT INTO sessions(token, user_id, created_at) VALUES (?, NULL, '2026-03-15T12:00:00')",
                 (token,))
    return token, True


def page(handler):
    """Open the episode DB, resolve session + user, run the handler, commit on success."""

    @functools.wraps(handler)
    async def wrapper(request):
        conn = connect(episode_db_path(request.app.state.data_dir, request.cookies.get(EPISODE_COOKIE)))
        try:
            token, is_new = _ensure_session(conn, request.cookies.get(SESSION_COOKIE))
            request.state.conn = conn
            request.state.session_token = token
            request.state.user = _load_user(conn, token)
            response = await handler(request)
            conn.commit()
            if is_new:
                response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax", path="/")
            return response
        finally:
            conn.close()

    return wrapper


def cart_count(conn, token: str) -> int:
    row = conn.execute("SELECT COALESCE(SUM(qty), 0) FROM cart_items WHERE session_token = ?", (token,)).fetchone()
    return row[0]


def render(request, name: str, status: int = 200, **ctx) -> HTMLResponse:
    conn = request.state.conn
    base = {
        "user": request.state.user,
        "cart_count": cart_count(conn, request.state.session_token),
        "categories": conn.execute("SELECT slug, name FROM categories ORDER BY name").fetchall(),
        "notice": request.query_params.get("notice"),
        "path": request.url.path,
    }
    return templates.TemplateResponse(request, name, {**base, **ctx}, status_code=status)


def redirect(url: str, notice: str | None = None, status: int = 303) -> RedirectResponse:
    if notice:
        from urllib.parse import urlencode
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}{urlencode({'notice': notice})}"
    return RedirectResponse(url, status_code=status)


def require_user(request) -> Response | None:
    if request.state.user is None:
        return redirect("/login?notice=Please+log+in+first")
    return None


def require_admin(request) -> Response | None:
    user = request.state.user
    if user is None:
        return redirect("/login?notice=Please+log+in+first")
    if not user["is_admin"]:
        return HTMLResponse(render_forbidden(request), status_code=403)
    return None


def render_forbidden(request) -> str:
    return templates.get_template("forbidden.html").render(request=request, user=request.state.user,
                                                          cart_count=0, categories=[], notice=None,
                                                          path=request.url.path)

