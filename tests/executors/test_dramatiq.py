"""Tests for dramatiq_executor."""

import pytest
from unittest.mock import Mock

pytest.importorskip("dramatiq")

from airlock import Intent


def make_intent(task, args=(), kwargs=None, dispatch_options=None):
    return Intent(
        task=task,
        args=args,
        kwargs=kwargs or {},
        dispatch_options=dispatch_options,
    )


def test_dramatiq_executor_with_send_with_options():
    """Test dramatiq_executor uses send_with_options when available."""
    from airlock.integrations.executors.dramatiq import dramatiq_executor

    mock_task = Mock()
    mock_task.send_with_options = Mock()
    intent = make_intent(mock_task, args=(1, 2), kwargs={"x": 3})

    dramatiq_executor(intent)

    mock_task.send_with_options.assert_called_once_with(
        args=(1, 2),
        kwargs={"x": 3}
    )


def test_dramatiq_executor_with_send_with_options_and_dispatch_options():
    """Test dramatiq_executor passes dispatch_options to send_with_options."""
    from airlock.integrations.executors.dramatiq import dramatiq_executor

    mock_task = Mock()
    mock_task.send_with_options = Mock()
    intent = make_intent(
        mock_task,
        args=(1,),
        kwargs={"y": 2},
        dispatch_options={"delay": 5000, "max_retries": 3}
    )

    dramatiq_executor(intent)

    mock_task.send_with_options.assert_called_once_with(
        args=(1,),
        kwargs={"y": 2},
        delay=5000,
        max_retries=3
    )


def test_dramatiq_executor_with_send():
    """Test dramatiq_executor uses send when send_with_options not available."""
    from airlock.integrations.executors.dramatiq import dramatiq_executor

    mock_task = Mock(spec=[])  # No send_with_options
    mock_task.send = Mock()
    intent = make_intent(mock_task, args=(1, 2), kwargs={"x": 3})

    dramatiq_executor(intent)

    mock_task.send.assert_called_once_with(1, 2, x=3)


def test_dramatiq_executor_fallback_to_sync():
    """Test dramatiq_executor falls back to sync for plain callables."""
    from airlock.integrations.executors.dramatiq import dramatiq_executor

    mock_task = Mock(spec=[])  # Plain callable
    intent = make_intent(mock_task, args=(1,), kwargs={"x": 2})

    dramatiq_executor(intent)

    mock_task.assert_called_once_with(1, x=2)


def test_dramatiq_executor_prefers_send_with_options_over_send():
    """Test dramatiq_executor prefers send_with_options when both exist."""
    from airlock.integrations.executors.dramatiq import dramatiq_executor

    mock_task = Mock()
    mock_task.send_with_options = Mock()
    mock_task.send = Mock()
    intent = make_intent(mock_task, args=(1,))

    dramatiq_executor(intent)

    mock_task.send_with_options.assert_called_once()
    mock_task.send.assert_not_called()


def test_dramatiq_executor_implements_protocol():
    """Test dramatiq_executor implements the Executor protocol."""
    from airlock import Executor
    from airlock.integrations.executors.dramatiq import dramatiq_executor

    assert isinstance(dramatiq_executor, Executor)
