"""Episode isolation: every episode gets its own copy of the seeded database.

Layout under the data dir:
  templates/seed-<seed>.db            pristine seeded database (built once per seed)
  episodes/<token>/shop.db            live database the browser talks to
  episodes/<token>/initial.db         snapshot taken after task setup, used by checkers
"""

import os
import secrets
import shutil
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from shopgym.app.db import connect
from shopgym.app.seed import build_database
from shopgym.config import EPISODE_COOKIE, SESSION_COOKIE

SetupFn = Callable[[sqlite3.Connection, str], None]


@dataclass(frozen=True)
class Episode:
    token: str
    root: Path
    db: Path
    initial: Path
    session_token: str

    @property
    def cookies(self) -> dict[str, str]:
        return {EPISODE_COOKIE: self.token, SESSION_COOKIE: self.session_token}


def template_path(data_dir: Path, seed: int) -> Path:
    path = data_dir / "templates" / f"seed-{seed}.db"
    if not path.exists():
        # Parallel episodes may race to build the same template: each builder writes its own temp file,
        # and the atomic rename means whichever finishes last simply replaces an identical file.
        tmp = path.with_name(f".{secrets.token_hex(8)}.tmp")
        build_database(tmp, seed)
        os.replace(tmp, path)
    return path


def create_episode(data_dir: Path, seed: int, setup: SetupFn | None = None) -> Episode:
    token = secrets.token_hex(16)
    session_token = secrets.token_hex(16)
    root = data_dir / "episodes" / token
    root.mkdir(parents=True)
    db, initial = root / "shop.db", root / "initial.db"
    shutil.copyfile(template_path(data_dir, seed), db)
    conn = connect(db)
    try:
        conn.execute("INSERT INTO sessions(token, user_id, created_at) VALUES (?, NULL, '2026-03-15T12:00:00')",
                     (session_token,))
        if setup:
            setup(conn, session_token)
        conn.commit()
    finally:
        conn.close()
    shutil.copyfile(db, initial)
    return Episode(token=token, root=root, db=db, initial=initial, session_token=session_token)


def remove_episode(episode: Episode) -> None:
    shutil.rmtree(episode.root, ignore_errors=True)
