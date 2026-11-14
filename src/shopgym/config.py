"""Shared constants. Everything that is not a secret lives here."""

import os
from pathlib import Path

SERVE_PORT = 4200
TEST_PORT = 4201
DEFAULT_DATA_DIR = "data"
SEED_DEFAULT = 7
# Fixed "current" date for the shop. Never use wall-clock time: it would break determinism.
SHOP_NOW = "2026-03-15T12:00:00"
SESSION_COOKIE = "sg_session"
EPISODE_COOKIE = "sg_episode"
PAGE_SIZE = 12
REVIEW_PAGE_SIZE = 5
SHIPPING_CENTS = 499
FREE_SHIPPING_THRESHOLD_CENTS = 5000
DEMO_PASSWORD = "password123"
# Public deployment limits (see app/live.py and app/limits.py). Used only when SHOPGYM_LIVE=1.
LIVE_MAX_COPIES = 200
LIVE_IDLE_MINUTES = 30
LIVE_NEW_COPIES_PER_HOUR_PER_IP = 10
LIVE_WRITES_PER_MINUTE_PER_IP = 60
MAX_BODY_BYTES = 16 * 1024


def live_mode() -> bool:
    """True for the public deployment: per-visitor database copies, limits, capacity cap."""
    return os.environ.get("SHOPGYM_LIVE", "") == "1"


def data_dir() -> Path:
    """Root for seed templates, episode databases and run outputs."""
    return Path(os.environ.get("SHOPGYM_DATA_DIR", DEFAULT_DATA_DIR)).resolve()
