"""Tests for huey_executor."""

import pytest
from unittest.mock import Mock

pytest.importorskip("huey")

from airlock import Intent


def make_intent(task, args=(), kwargs=None, dispatch_options=None):
    return Intent(
        task=task,
        args=args,
        kwargs=kwargs or {},
        dispatch_options=dispatch_options,
    )


def test_huey_executor_with_schedule():
    """Test huey_executor uses schedule method."""
    from airlock.integrations.executors.huey import huey_executor

    mock_task = Mock()
    mock_task.schedule = Mock()
    intent = make_intent(mock_task, args=(1, 2), kwargs={"x": 3})

    huey_executor(intent)

    mock_task.schedule.assert_called_once_with(
        args=(1, 2),
        kwargs={"x": 3}
    )


def test_huey_executor_with_dispatch_options():
    """Test huey_executor passes dispatch_options to schedule."""
    from airlock.integrations.executors.huey import huey_executor

    mock_task = Mock()
    mock_task.schedule = Mock()
    intent = make_intent(
        mock_task,
        args=(1,),
        kwargs={"y": 2},
        dispatch_options={"delay": 60, "eta": "2025-01-01"}
    )

    huey_executor(intent)

    mock_task.schedule.assert_called_once_with(
        args=(1,),
        kwargs={"y": 2},
        delay=60,
        eta="2025-01-01"
    )


def test_huey_executor_fallback_to_sync():
    """Test huey_executor falls back to sync for plain callables."""
    from airlock.integrations.executors.huey import huey_executor

    mock_task = Mock(spec=[])  # Plain callable
    intent = make_intent(mock_task, args=(1,), kwargs={"x": 2})

    huey_executor(intent)

    mock_task.assert_called_once_with(1, x=2)


def test_huey_executor_no_dispatch_options():
    """Test huey_executor works without dispatch_options."""
    from airlock.integrations.executors.huey import huey_executor

    mock_task = Mock()
    mock_task.schedule = Mock()
    intent = make_intent(mock_task, args=(1,))

    huey_executor(intent)

    mock_task.schedule.assert_called_once_with(args=(1,), kwargs={})


def test_huey_executor_implements_protocol():
    """Test huey_executor implements the Executor protocol."""
    from airlock import Executor
    from airlock.integrations.executors.huey import huey_executor

    assert isinstance(huey_executor, Executor)
