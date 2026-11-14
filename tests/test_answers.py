"""Answer matching: equivalent phrasings pass, answers that mean something else fail."""

import pytest

from shopgym.env.episodes import create_episode
from shopgym.tasks.answers import (count_answer, money_answer, product_name_given, refusal_given,
                                   sku_given, status_matches)
from shopgym.tasks.checkers import CheckContext
from shopgym.tasks.registry import load_tasks

TASKS = load_tasks()


@pytest.mark.parametrize("answer", ["3", " 3. ", "three", "3 reviews", "Answer: 3", "3 of 12", "Three."])
def test_count_accepts_equivalent_forms(answer):
    assert count_answer(answer) == 3


@pytest.mark.parametrize("answer", ["", "none", "12", "3 or 4", "not 3", "3,12", "2.5", "three hundred", "12 of 3"])
def test_count_rejects_other_or_ambiguous_answers(answer):
    assert count_answer(answer) != 3


@pytest.mark.parametrize("answer", ["$1,299.00", "1299", "USD 1,299", "$1299.0", "1,299.00 dollars"])
def test_money_accepts_formats(answer):
    assert money_answer(answer) == pytest.approx(1299)


@pytest.mark.parametrize("answer", ["$1,298", "1299 or 1399", "not $1299", ""])
def test_money_rejects_wrong_or_ambiguous(answer):
    assert money_answer(answer) != pytest.approx(1299) or money_answer(answer) is None


@pytest.mark.parametrize("answer", ["shipped", "Shipped.", "Status: shipped", "The order is shipped."])
def test_status_accepts_phrasings(answer):
    assert status_matches(answer, "shipped", {"shipped", "processing", "delivered"})


@pytest.mark.parametrize("answer", ["processing", "not shipped", "shipped, then delivered", "", "done"])
def test_status_rejects_wrong_negated_or_mixed(answer):
    assert not status_matches(answer, "shipped", {"shipped", "processing", "delivered"})


def test_status_treats_canceled_as_cancelled():
    assert status_matches("Canceled", "cancelled", {"cancelled", "shipped"})


@pytest.mark.parametrize("answer", ["not cancellable", "can't be cancelled", "Cannot be cancelled.",
                                    "can’t be cancelled", "It can not be canceled", "non-cancellable"])
def test_refusal_accepts_phrasings(answer):
    assert refusal_given(answer)


@pytest.mark.parametrize("answer", ["done", "", "It was cancelled", "not refunded"])
def test_refusal_rejects_other_answers(answer):
    assert not refusal_given(answer)


def test_product_name_must_be_the_longest_mention():
    names = ["Desk Lamp", "Desk Lamp Pro"]
    assert product_name_given("Desk Lamp", {"Desk Lamp"}, names)
    assert product_name_given("The cheapest is the Desk Lamp.", {"Desk Lamp"}, names)
    assert not product_name_given("Desk Lamp Pro", {"Desk Lamp"}, names)
    assert not product_name_given("Desk Lamp or Desk Lamp Pro", {"Desk Lamp"}, names)


def test_sku_is_case_insensitive_and_single():
    assert sku_given("bok-atl-01.", "BOK-ATL-01")
    assert sku_given("SKU: BOK-ATL-01", "BOK-ATL-01")
    assert not sku_given("BOK-ATL-01 or BOK-ATL-02", "BOK-ATL-01")


def test_order_status_needs_a_login_during_the_episode(data_dir):
    task = TASKS["order-status-after-login"]
    ep = create_episode(data_dir, task.seed, task.make_setup())
    ctx = CheckContext(initial=ep.initial, final=ep.db, answer="shipped")
    verdict = task.evaluate(ctx)
    assert not verdict.ok and "never logged in" in verdict.reason
