"""Per-visitor database copies for the public deployment.

Every visitor gets their own copy of the seeded database, identified by the `sg_episode` cookie.
Copies are capped in number, expire after an idle period, and each client address may create only
a few copies per hour. When the cap is reached new visitors get a 503 instead of evicting someone.
"""

import os
import secrets
import shutil
import time
from collections.abc import Callable
from pathlib import Path

from shopgym.app.limits import RateLimiter
from shopgym.config import SEED_DEFAULT
from shopgym.env.episodes import template_path

EPISODE_DIR = "episodes"
DB_NAME = "shop.db"


class LiveRegistry:
    def __init__(self, data_dir: Path, max_copies: int, idle_seconds: float, new_per_hour_per_ip: int,
                 clock: Callable[[], float] = time.time):
        self.data_dir = Path(data_dir)
        self.max_copies = max_copies
        self.idle_seconds = idle_seconds
        self.clock = clock
        self.creations = RateLimiter(new_per_hour_per_ip, 3600.0)

    def _root(self, token: str) -> Path:
        return self.data_dir / EPISODE_DIR / token

    def touch(self, token: str | None) -> Path | None:
        """Return the copy's database path for a live token, refreshing its idle clock; else None."""
        if not token or not _is_token(token):
            return None
        root = self._root(token)
        db = root / DB_NAME
        if not db.exists():
            return None
        os.utime(root, None)
        return db

    def sweep(self) -> int:
        """Delete copies idle longer than the expiry. Returns how many were removed."""
        base = self.data_dir / EPISODE_DIR
        if not base.exists():
            return 0
        now, removed = self.clock(), 0
        for root in base.iterdir():
            if root.is_dir() and now - root.stat().st_mtime > self.idle_seconds:
                shutil.rmtree(root, ignore_errors=True)
                removed += 1
        return removed

    def live_count(self) -> int:
        base = self.data_dir / EPISODE_DIR
        return sum(1 for p in base.iterdir() if p.is_dir()) if base.exists() else 0

    def create(self, client: str) -> str | None:
        """Copy the seed for a new visitor. None when the cap is reached or this client is rate limited."""
        if not self.creations.allow(client):
            return None
        self.sweep()
        if self.live_count() >= self.max_copies:
            return None
        token = secrets.token_hex(16)
        root = self._root(token)
        root.mkdir(parents=True)
        shutil.copyfile(template_path(self.data_dir, SEED_DEFAULT), root / DB_NAME)
        return token


def _is_token(token: str) -> bool:
    return len(token) == 32 and all(c in "0123456789abcdef" for c in token)
