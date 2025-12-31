"""
Comprehensive tests for airlock executors.

Tests all built-in executors (sync, celery, django-q, huey, dramatiq)
and their behavior with various task types.
"""

import pytest
from unittest.mock import MagicMock, Mock, patch, call

from airlock import Intent


# =============================================================================
# Test Helpers
# =============================================================================


def make_intent(task, args=(), kwargs=None, dispatch_options=None):
    """Helper to create Intent objects for testing."""
    return Intent(
        task=task,
        args=args,
        kwargs=kwargs or {},
        dispatch_options=dispatch_options,
    )


# =============================================================================
# sync_executor tests
# =============================================================================


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


# =============================================================================
# celery_executor tests
# =============================================================================


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

    mock_task = Mock()
    mock_task.delay = Mock()
    # No apply_async attribute
    delattr(type(mock_task), 'apply_async') if hasattr(mock_task, 'apply_async') else None
    intent = make_intent(mock_task, args=(1, 2), kwargs={"x": 3})

    celery_executor(intent)

    mock_task.delay.assert_called_once_with(1, 2, x=3)


def test_celery_executor_fallback_to_sync():
    """Test celery_executor falls back to sync for plain callables."""
    from airlock.integrations.executors.celery import celery_executor

    mock_task = Mock()
    # Plain callable (no delay or apply_async)
    intent = make_intent(mock_task, args=(1,), kwargs={"x": 2})

    celery_executor(intent)

    # Should call directly
    mock_task.assert_called_once_with(1, x=2)


def test_celery_executor_prefers_apply_async_over_delay():
    """Test celery_executor prefers apply_async when both exist."""
    from airlock.integrations.executors.celery import celery_executor

    mock_task = Mock()
    mock_task.apply_async = Mock()
    mock_task.delay = Mock()
    intent = make_intent(mock_task, args=(1,))

    celery_executor(intent)

    # Should use apply_async, not delay
    mock_task.apply_async.assert_called_once()
    mock_task.delay.assert_not_called()


# =============================================================================
# django_q_executor tests
# =============================================================================


def test_django_q_executor_basic():
    """Test django_q_executor calls async_task."""
    from airlock.integrations.executors.django_q import django_q_executor

    with patch("airlock.integrations.executors.django_q.async_task") as mock_async_task:
        mock_task = Mock(__name__="my_task")
        intent = make_intent(mock_task, args=(1, 2), kwargs={"x": 3})

        django_q_executor(intent)

        mock_async_task.assert_called_once_with(mock_task, 1, 2, x=3)


def test_django_q_executor_with_dispatch_options():
    """Test django_q_executor passes dispatch_options to async_task."""
    from airlock.integrations.executors.django_q import django_q_executor

    with patch("airlock.integrations.executors.django_q.async_task") as mock_async_task:
        mock_task = Mock(__name__="my_task")
        intent = make_intent(
            mock_task,
            args=(1,),
            kwargs={"y": 2},
            dispatch_options={"group": "emails", "timeout": 60, "hook": "my_hook"}
        )

        django_q_executor(intent)

        mock_async_task.assert_called_once_with(
            mock_task,
            1,
            y=2,
            group="emails",
            timeout=60,
            hook="my_hook"
        )


def test_django_q_executor_no_args():
    """Test django_q_executor with no arguments."""
    from airlock.integrations.executors.django_q import django_q_executor

    with patch("airlock.integrations.executors.django_q.async_task") as mock_async_task:
        mock_task = Mock(__name__="my_task")
        intent = make_intent(mock_task)

        django_q_executor(intent)

        mock_async_task.assert_called_once_with(mock_task)


def test_django_q_executor_no_dispatch_options():
    """Test django_q_executor works without dispatch_options."""
    from airlock.integrations.executors.django_q import django_q_executor

    with patch("airlock.integrations.executors.django_q.async_task") as mock_async_task:
        mock_task = Mock(__name__="my_task")
        intent = make_intent(mock_task, args=(1,), dispatch_options=None)

        django_q_executor(intent)

        mock_async_task.assert_called_once_with(mock_task, 1)


# =============================================================================
# huey_executor tests
# =============================================================================


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

    mock_task = Mock()
    # Plain callable (no schedule method)
    intent = make_intent(mock_task, args=(1,), kwargs={"x": 2})

    huey_executor(intent)

    # Should call directly
    mock_task.assert_called_once_with(1, x=2)


def test_huey_executor_no_dispatch_options():
    """Test huey_executor works without dispatch_options."""
    from airlock.integrations.executors.huey import huey_executor

    mock_task = Mock()
    mock_task.schedule = Mock()
    intent = make_intent(mock_task, args=(1,))

    huey_executor(intent)

    mock_task.schedule.assert_called_once_with(args=(1,), kwargs={})


# =============================================================================
# dramatiq_executor tests
# =============================================================================


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

    mock_task = Mock()
    mock_task.send = Mock()
    # No send_with_options attribute
    intent = make_intent(mock_task, args=(1, 2), kwargs={"x": 3})

    dramatiq_executor(intent)

    mock_task.send.assert_called_once_with(1, 2, x=3)


def test_dramatiq_executor_fallback_to_sync():
    """Test dramatiq_executor falls back to sync for plain callables."""
    from airlock.integrations.executors.dramatiq import dramatiq_executor

    mock_task = Mock()
    # Plain callable (no send or send_with_options)
    intent = make_intent(mock_task, args=(1,), kwargs={"x": 2})

    dramatiq_executor(intent)

    # Should call directly
    mock_task.assert_called_once_with(1, x=2)


def test_dramatiq_executor_prefers_send_with_options_over_send():
    """Test dramatiq_executor prefers send_with_options when both exist."""
    from airlock.integrations.executors.dramatiq import dramatiq_executor

    mock_task = Mock()
    mock_task.send_with_options = Mock()
    mock_task.send = Mock()
    intent = make_intent(mock_task, args=(1,))

    dramatiq_executor(intent)

    # Should use send_with_options, not send
    mock_task.send_with_options.assert_called_once()
    mock_task.send.assert_not_called()


# =============================================================================
# Executor Protocol tests
# =============================================================================


def test_sync_executor_implements_protocol():
    """Test sync_executor implements the Executor protocol."""
    from airlock import Executor
    from airlock.integrations.executors.sync import sync_executor

    assert isinstance(sync_executor, Executor)


def test_celery_executor_implements_protocol():
    """Test celery_executor implements the Executor protocol."""
    from airlock import Executor
    from airlock.integrations.executors.celery import celery_executor

    assert isinstance(celery_executor, Executor)


def test_django_q_executor_implements_protocol():
    """Test django_q_executor implements the Executor protocol."""
    from airlock import Executor
    from airlock.integrations.executors.django_q import django_q_executor

    assert isinstance(django_q_executor, Executor)


def test_huey_executor_implements_protocol():
    """Test huey_executor implements the Executor protocol."""
    from airlock import Executor
    from airlock.integrations.executors.huey import huey_executor

    assert isinstance(huey_executor, Executor)


def test_dramatiq_executor_implements_protocol():
    """Test dramatiq_executor implements the Executor protocol."""
    from airlock import Executor
    from airlock.integrations.executors.dramatiq import dramatiq_executor

    assert isinstance(dramatiq_executor, Executor)


def test_custom_executor_protocol():
    """Test custom function implementing Executor protocol."""
    from airlock import Executor, Intent

    def custom_executor(intent: Intent) -> None:
        # Custom logic here
        pass

    assert isinstance(custom_executor, Executor)
