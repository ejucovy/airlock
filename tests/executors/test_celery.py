"""Tests for celery_executor."""

import pytest
from unittest.mock import Mock

pytest.importorskip("celery")

from airlock import Intent


def make_intent(task, args=(), kwargs=None, dispatch_options=None):
    return Intent(
        task=task,
        args=args,
        kwargs=kwargs or {},
        dispatch_options=dispatch_options,
    )


def test_celery_executor_with_apply_async():
    """Test celery_executor uses apply_async when available."""
    from airlock.integrations.executors.celery import celery_executor

    mock_task = Mock()
    mock_task.apply_async = Mock()
    intent = make_intent(mock_task, args=(1, 2), kwargs={"x": 3})

    celery_executor(intent)

    mock_task.apply_async.assert_called_once_with(
        args=(1, 2),
        kwargs={"x": 3}
    )


def test_celery_executor_with_apply_async_and_options():
    """Test celery_executor passes dispatch_options to apply_async."""
    from airlock.integrations.executors.celery import celery_executor

    mock_task = Mock()
    mock_task.apply_async = Mock()
    intent = make_intent(
        mock_task,
        args=(1,),
        kwargs={"y": 2},
        dispatch_options={"countdown": 60, "queue": "high"}
    )

    celery_executor(intent)

    mock_task.apply_async.assert_called_once_with(
        args=(1,),
        kwargs={"y": 2},
        countdown=60,
        queue="high"
    )


def test_celery_executor_with_delay():
    """Test celery_executor uses delay when apply_async not available."""
    from airlock.integrations.executors.celery import celery_executor

    mock_task = Mock(spec=[])  # No apply_async
    mock_task.delay = Mock()
    intent = make_intent(mock_task, args=(1, 2), kwargs={"x": 3})

    celery_executor(intent)

    mock_task.delay.assert_called_once_with(1, 2, x=3)


def test_celery_executor_fallback_to_sync():
    """Test celery_executor falls back to sync for plain callables."""
    from airlock.integrations.executors.celery import celery_executor

    mock_task = Mock(spec=[])  # Plain callable
    intent = make_intent(mock_task, args=(1,), kwargs={"x": 2})

    celery_executor(intent)

    mock_task.assert_called_once_with(1, x=2)


def test_celery_executor_prefers_apply_async_over_delay():
    """Test celery_executor prefers apply_async when both exist."""
    from airlock.integrations.executors.celery import celery_executor

    mock_task = Mock()
    mock_task.apply_async = Mock()
    mock_task.delay = Mock()
    intent = make_intent(mock_task, args=(1,))

    celery_executor(intent)

    mock_task.apply_async.assert_called_once()
    mock_task.delay.assert_not_called()


def test_celery_executor_implements_protocol():
    """Test celery_executor implements the Executor protocol."""
    from airlock import Executor
    from airlock.integrations.executors.celery import celery_executor

    assert isinstance(celery_executor, Executor)
