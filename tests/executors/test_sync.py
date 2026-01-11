"""Tests for sync_executor."""

import pytest
from unittest.mock import Mock

from airlock import Intent


def make_intent(task, args=(), kwargs=None, dispatch_options=None):
    """Helper to create Intent objects for testing."""
    return Intent(
        task=task,
        args=args,
        kwargs=kwargs or {},
        dispatch_options=dispatch_options,
    )


def test_sync_executor_plain_callable():
    """Test sync_executor with a plain function."""
    from airlock.integrations.executors.sync import sync_executor

    mock_task = Mock(return_value="result")
    intent = make_intent(mock_task, args=(1, 2), kwargs={"x": 3})

    sync_executor(intent)

    mock_task.assert_called_once_with(1, 2, x=3)


def test_sync_executor_no_args():
    """Test sync_executor with no arguments."""
    from airlock.integrations.executors.sync import sync_executor

    mock_task = Mock()
    intent = make_intent(mock_task)

    sync_executor(intent)

    mock_task.assert_called_once_with()


def test_sync_executor_ignores_dispatch_options():
    """Test that sync_executor ignores dispatch_options."""
    from airlock.integrations.executors.sync import sync_executor

    mock_task = Mock()
    intent = make_intent(
        mock_task,
        args=(1,),
        dispatch_options={"countdown": 60, "queue": "high"}
    )

    sync_executor(intent)

    # Should call task directly, ignoring dispatch_options
    mock_task.assert_called_once_with(1)


def test_sync_executor_with_exception():
    """Test sync_executor propagates exceptions from tasks."""
    from airlock.integrations.executors.sync import sync_executor

    def failing_task():
        raise ValueError("boom")

    intent = make_intent(failing_task)

    with pytest.raises(ValueError, match="boom"):
        sync_executor(intent)


def test_sync_executor_implements_protocol():
    """Test sync_executor implements the Executor protocol."""
    from airlock import Executor
    from airlock.integrations.executors.sync import sync_executor

    assert isinstance(sync_executor, Executor)
