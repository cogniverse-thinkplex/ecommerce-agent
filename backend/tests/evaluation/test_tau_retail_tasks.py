import pytest

from app.evaluation.tau_retail_tasks import (
    load_retail_task_summaries,
    load_retail_task_summary,
)


def test_load_retail_task_summaries_exposes_user_goal_and_expected_actions():
    tasks = load_retail_task_summaries(limit=1)

    assert len(tasks) == 1
    task = tasks[0]
    assert task.task_id == "0"
    assert "exchange the mechanical keyboard" in task.reason_for_call
    assert task.known_info == "You are Yusuf Rossi in zip code 19122."
    assert task.reward_basis == ["DB", "NL_ASSERTION"]
    assert [action.name for action in task.expected_actions] == [
        "find_user_id_by_name_zip",
        "get_order_details",
        "get_product_details",
        "get_product_details",
        "exchange_delivered_order_items",
    ]


def test_load_retail_task_summary_returns_one_task_by_id():
    task = load_retail_task_summary("0")

    assert task.task_id == "0"
    assert task.expected_actions[0].arguments == {
        "first_name": "Yusuf",
        "last_name": "Rossi",
        "zip": "19122",
    }


def test_load_retail_task_summary_raises_for_missing_task_id():
    with pytest.raises(KeyError, match="Unknown retail task_id"):
        load_retail_task_summary("missing")
