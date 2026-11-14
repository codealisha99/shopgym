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


def data_dir() -> Path:
    """Root for seed templates, episode databases and run outputs."""
    return Path(os.environ.get("SHOPGYM_DATA_DIR", DEFAULT_DATA_DIR)).resolve()
