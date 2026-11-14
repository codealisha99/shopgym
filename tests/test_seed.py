import hashlib

from shopgym.app.db import connect
from shopgym.app.seed import build_database


def _digest(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_same_seed_builds_identical_database(tmp_path):
    a = build_database(tmp_path / "a.db", seed=7)
    b = build_database(tmp_path / "b.db", seed=7)
    assert _digest(a) == _digest(b)


def test_different_seed_changes_filler_data(tmp_path):
    a = build_database(tmp_path / "a.db", seed=7)
    b = build_database(tmp_path / "b.db", seed=8)
    assert _digest(a) != _digest(b)


def test_anchor_facts_hold_for_every_seed(tmp_path):
    for seed in (1, 7, 42):
        conn = connect(build_database(tmp_path / f"s{seed}.db", seed=seed))
        ada = conn.execute("SELECT id FROM users WHERE email='ada@shop.test'").fetchone()[0]
        ada_orders = conn.execute("SELECT number, status FROM orders WHERE user_id=? ORDER BY created_at DESC",
                                  (ada,)).fetchall()
        assert [r["number"] for r in ada_orders] == [1043, 1042, 1044]  # 1043 is the most recent
        assert conn.execute("SELECT stock FROM products WHERE sku='CLO-TRP-01'").fetchone()[0] == 20
        filler_owners = conn.execute("SELECT COUNT(*) FROM orders WHERE user_id = ? AND number NOT IN (1042,1043,1044)",
                                     (ada,)).fetchone()[0]
        assert filler_owners == 0
        conn.close()
