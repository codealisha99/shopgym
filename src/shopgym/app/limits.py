"""Abuse limits for the public deployment: request body size and per-client write rate.

Both are plain ASGI middleware with in-memory state, so the server must run as one process.
The client address comes from the last X-Forwarded-For entry (the one the platform proxy
appends), falling back to the socket peer. Only the platform proxy may set that header.
"""

import time
from collections import defaultdict, deque

from starlette.responses import PlainTextResponse

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class _BodyTooLarge(Exception):
    pass


def client_ip(scope) -> str:
    for name, value in scope.get("headers", []):
        if name == b"x-forwarded-for":
            parts = value.decode("latin-1").split(",")
            return parts[-1].strip() or "unknown"
    client = scope.get("client")
    return client[0] if client else "unknown"


class RateLimiter:
    """Sliding-window counter per key: at most `limit` events in the last `window` seconds."""

    def __init__(self, limit: int, window: float, clock=time.monotonic):
        self.limit, self.window, self.clock = limit, window, clock
        self._events: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = self.clock()
        events = self._events[key]
        while events and now - events[0] >= self.window:
            events.popleft()
        if len(events) >= self.limit:
            return False
        events.append(now)
        return True


class BodyLimit:
    """Reject requests whose body exceeds `max_bytes` (by Content-Length, and by bytes actually read)."""

    def __init__(self, app, max_bytes: int):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        for name, value in scope.get("headers", []):
            if name == b"content-length" and value.isdigit() and int(value) > self.max_bytes:
                return await _reject(scope, receive, send, 413, "Request body too large.")
        seen = 0
        started = False

        async def limited_receive():
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > self.max_bytes:
                    raise _BodyTooLarge()
            return message

        async def tracking_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except _BodyTooLarge:
            if started:
                raise
            await _reject(scope, receive, send, 413, "Request body too large.")


class WriteRateLimit:
    """Limit state-changing requests per client address."""

    def __init__(self, app, limiter: RateLimiter):
        self.app, self.limiter = app, limiter

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["method"] in WRITE_METHODS:
            if not self.limiter.allow(client_ip(scope)):
                return await _reject(scope, receive, send, 429, "Too many requests. Wait a minute and retry.")
        await self.app(scope, receive, send)


async def _reject(scope, receive, send, status: int, text: str):
    response = PlainTextResponse(text, status_code=status, headers={"Retry-After": "60"})
    await response(scope, receive, send)
