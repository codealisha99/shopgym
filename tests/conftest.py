import threading
import time
from pathlib import Path

import pytest
import uvicorn
from starlette.testclient import TestClient

from shopgym.app.server import make_app
from shopgym.config import TEST_PORT
from shopgym.env.episodes import create_episode


@pytest.fixture()
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"


@pytest.fixture()
def episode(data_dir):
    return create_episode(data_dir, seed=7)


@pytest.fixture()
def client(data_dir, episode):
    """TestClient bound to a fresh isolated episode database (no browser needed)."""
    c = TestClient(make_app(data_dir), follow_redirects=False)
    for name, value in episode.cookies.items():
        c.cookies.set(name, value)
    c.episode = episode
    return c


@pytest.fixture(scope="session")
def live_server(tmp_path_factory):
    """The real server on a real port, for browser tests. Shared by the whole session."""
    data = tmp_path_factory.mktemp("live") / "data"
    config = uvicorn.Config(make_app(data), host="127.0.0.1", port=TEST_PORT, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.1)
    yield {"base_url": f"http://127.0.0.1:{TEST_PORT}", "data_dir": data}
    server.should_exit = True
    thread.join(timeout=10)
