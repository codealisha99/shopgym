"""Every checker: no-op must fail, a deliberate wrong change must fail, the right change must pass."""

import sqlite3

import pytest

from shopgym.env.episodes import create_episode
from shopgym.tasks.checkers import CheckContext
from shopgym.tasks.registry import load_tasks

TASKS = load_tasks()


def _episode_for(data_dir, task_id):
    task = TASKS[task_id]
    return task, create_episode(data_dir, task.seed, task.make_setup())


def _mutate(ep, sql: str, args=()):
    conn = sqlite3.connect(ep.db)
    conn.execute(sql, args)
    conn.commit()
    conn.close()


def _verdict(task, ep, answer=None):
    return task.evaluate(CheckContext(initial=ep.initial, final=ep.db, answer=answer))


@pytest.mark.parametrize("task_id", sorted(TASKS))
def test_noop_fails_every_task(data_dir, task_id):
    task, ep = _episode_for(data_dir, task_id)
    assert not _verdict(task, ep, answer="").ok


@pytest.mark.parametrize("task_id", sorted(TASKS))
def test_unchanged_database_with_no_answer_fails_every_task(data_dir, task_id):
    task, ep = _episode_for(data_dir, task_id)
    assert not _verdict(task, ep, answer=None).ok


def test_cancel_wrong_order_fails(data_dir):
    task, ep = _episode_for(data_dir, "cancel-order-1042")
    _mutate(ep, "UPDATE orders SET status='cancelled' WHERE number=1043")
    _mutate(ep, "UPDATE orders SET status='cancelled' WHERE number=1042")
    verdict = _verdict(task, ep)
    assert not verdict.ok and "orders:1043" in verdict.reason


def test_cancel_right_order_passes(data_dir):
    task, ep = _episode_for(data_dir, "cancel-order-1042")
    _mutate(ep, "UPDATE orders SET status='cancelled' WHERE number=1042")
    assert _verdict(task, ep).ok


def test_refund_wrong_customer_fails(data_dir):
    task, ep = _episode_for(data_dir, "admin-refund-disambiguated")
    _mutate(ep, "UPDATE orders SET status='refunded' WHERE number=1062")
    _mutate(ep, "INSERT INTO refunds(order_id, amount_cents, created_at)"
                " SELECT id, total_cents, '2026-03-15' FROM orders WHERE number=1062")
    _mutate(ep, "UPDATE orders SET status='refunded' WHERE number=1061")
    _mutate(ep, "INSERT INTO refunds(order_id, amount_cents, created_at)"
                " SELECT id, total_cents, '2026-03-15' FROM orders WHERE number=1061")
    assert not _verdict(task, ep).ok


def test_refund_right_order_passes(data_dir):
    task, ep = _episode_for(data_dir, "admin-refund-disambiguated")
    _mutate(ep, "UPDATE orders SET status='refunded' WHERE number=1061")
    _mutate(ep, "INSERT INTO refunds(order_id, amount_cents, created_at)"
                " SELECT id, total_cents, '2026-03-15' FROM orders WHERE number=1061")
    assert _verdict(task, ep).ok


def test_cart_with_wrong_quantity_fails(data_dir):
    task, ep = _episode_for(data_dir, "add-to-cart")
    _mutate(ep, "INSERT INTO cart_items(session_token, product_id, qty)"
                " SELECT ?, id, 1 FROM products WHERE sku='CLO-TRP-01'", (ep.session_token,))
    assert not _verdict(task, ep).ok
    _mutate(ep, "UPDATE cart_items SET qty=2")
    assert _verdict(task, ep).ok


def test_search_count_checks_the_number(data_dir):
    task, ep = _episode_for(data_dir, "search-count")
    truth = sqlite3.connect(ep.initial)
    count = truth.execute("SELECT COUNT(*) FROM products p WHERE (p.name LIKE '%lamp%' OR p.description LIKE '%lamp%')"
                          " AND p.active = 1").fetchone()[0]
    truth.close()
    assert _verdict(task, ep, answer=str(count)).ok
    assert not _verdict(task, ep, answer=str(count + 1)).ok


def test_cancel_refusal_needs_the_words_and_no_change(data_dir):
    task, ep = _episode_for(data_dir, "cancel-shipped-refusal")
    assert not _verdict(task, ep, answer="done").ok
    assert _verdict(task, ep, answer="not cancellable").ok
    _mutate(ep, "UPDATE orders SET status='cancelled' WHERE number=1044")
    assert not _verdict(task, ep, answer="not cancellable").ok


def test_side_effect_guard_catches_unrelated_writes(data_dir):
    task, ep = _episode_for(data_dir, "newsletter-subscribe")
    _mutate(ep, "INSERT INTO newsletter_subscribers(email, active, created_at)"
                " VALUES ('ada.new@example.test', 1, 'x')")
    _mutate(ep, "UPDATE orders SET status='refunded' WHERE number=1051")
    verdict = _verdict(task, ep)
    assert not verdict.ok and "orders:1051" in verdict.reason


def test_positive_newsletter_passes_when_only_the_subscription_changes(data_dir):
    task, ep = _episode_for(data_dir, "newsletter-subscribe")
    _mutate(ep, "INSERT INTO newsletter_subscribers(email, active, created_at)"
                " VALUES ('ada.new@example.test', 1, 'x')")
    assert _verdict(task, ep).ok
