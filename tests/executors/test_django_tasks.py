"""Tests for django_tasks_executor."""

import pytest
from unittest.mock import Mock, MagicMock

from airlock import Intent


def make_intent(task, args=(), kwargs=None, dispatch_options=None):
    return Intent(
        task=task,
        args=args,
        kwargs=kwargs or {},
        dispatch_options=dispatch_options,
    )


def test_django_tasks_executor_with_enqueue():
    """Test django_tasks_executor uses enqueue method."""
    from airlock.integrations.executors.django_tasks import django_tasks_executor

    mock_task = Mock()
    mock_task.enqueue = Mock()
    intent = make_intent(mock_task, args=(1, 2), kwargs={"x": 3})

    django_tasks_executor(intent)

    mock_task.enqueue.assert_called_once_with(1, 2, x=3)


def test_django_tasks_executor_with_dispatch_options():
    """Test django_tasks_executor passes dispatch_options via .using()."""
    from airlock.integrations.executors.django_tasks import django_tasks_executor

    # Create a mock that supports .using().enqueue() chaining
    mock_using_result = Mock()
    mock_using_result.enqueue = Mock()

    mock_task = Mock()
    mock_task.using = Mock(return_value=mock_using_result)
    mock_task.enqueue = Mock()

    intent = make_intent(
        mock_task,
        args=(1,),
        kwargs={"y": 2},
        dispatch_options={"priority": 50, "queue_name": "high"}
    )

    django_tasks_executor(intent)

    # Verify .using() was called with options
    mock_task.using.assert_called_once_with(priority=50, queue_name="high")
    # Verify .enqueue() was called on the result of .using()
    mock_using_result.enqueue.assert_called_once_with(1, y=2)
    # Verify original .enqueue() was NOT called directly
    mock_task.enqueue.assert_not_called()


def test_django_tasks_executor_with_run_after():
    """Test django_tasks_executor handles run_after option."""
    from airlock.integrations.executors.django_tasks import django_tasks_executor
    from datetime import datetime, timedelta

    run_after = datetime.now() + timedelta(hours=1)

    mock_using_result = Mock()
    mock_using_result.enqueue = Mock()

    mock_task = Mock()
    mock_task.using = Mock(return_value=mock_using_result)
    mock_task.enqueue = Mock()

    intent = make_intent(
        mock_task,
        args=("arg1",),
        kwargs={},
        dispatch_options={"run_after": run_after}
    )

    django_tasks_executor(intent)

    mock_task.using.assert_called_once_with(run_after=run_after)
    mock_using_result.enqueue.assert_called_once_with("arg1")


def test_django_tasks_executor_fallback_to_sync():
    """Test django_tasks_executor falls back to sync for plain callables."""
    from airlock.integrations.executors.django_tasks import django_tasks_executor

    mock_task = Mock(spec=[])  # Plain callable - no enqueue method
    intent = make_intent(mock_task, args=(1,), kwargs={"x": 2})

    django_tasks_executor(intent)

    mock_task.assert_called_once_with(1, x=2)


def test_django_tasks_executor_no_dispatch_options():
    """Test django_tasks_executor works without dispatch_options."""
    from airlock.integrations.executors.django_tasks import django_tasks_executor

    mock_task = Mock()
    mock_task.enqueue = Mock()
    mock_task.using = Mock()
    intent = make_intent(mock_task, args=(1,))

    django_tasks_executor(intent)

    # Should use .enqueue() directly without .using()
    mock_task.enqueue.assert_called_once_with(1)
    mock_task.using.assert_not_called()


def test_django_tasks_executor_empty_dispatch_options():
    """Test django_tasks_executor treats empty dict as no options."""
    from airlock.integrations.executors.django_tasks import django_tasks_executor

    mock_task = Mock()
    mock_task.enqueue = Mock()
    mock_task.using = Mock()
    intent = make_intent(mock_task, args=(1,), dispatch_options={})

    django_tasks_executor(intent)

    # Empty dict should not trigger .using()
    mock_task.enqueue.assert_called_once_with(1)
    mock_task.using.assert_not_called()


def test_django_tasks_executor_without_using_method():
    """Test django_tasks_executor handles tasks without .using() method."""
    from airlock.integrations.executors.django_tasks import django_tasks_executor

    # Task has .enqueue() but not .using() - options ignored
    mock_task = Mock(spec=['enqueue'])
    mock_task.enqueue = Mock()
    intent = make_intent(
        mock_task,
        args=(1,),
        dispatch_options={"priority": 50}
    )

    django_tasks_executor(intent)

    # Should still work, just using enqueue directly
    mock_task.enqueue.assert_called_once_with(1)


def test_django_tasks_executor_implements_protocol():
    """Test django_tasks_executor implements the Executor protocol."""
    from airlock import Executor
    from airlock.integrations.executors.django_tasks import django_tasks_executor

    assert isinstance(django_tasks_executor, Executor)


# =============================================================================
# Integration tests (scope + enqueue + executor)
# =============================================================================


def test_integration_dispatch_options_passed_through():
    """Test dispatch_options flow through scope/enqueue to task.using().enqueue()."""
    from airlock import scope, enqueue, AllowAll
    from airlock.integrations.executors.django_tasks import django_tasks_executor

    enqueue_calls = []
    using_calls = []

    class FakeDjangoTask:
        """Simulates a Django @task decorated function."""

        def __init__(self):
            self._options = {}

        def using(self, **options):
            using_calls.append(options)
            # Return a new instance with options
            new_task = FakeDjangoTask()
            new_task._options = options
            return new_task

        def enqueue(self, *args, **kwargs):
            enqueue_calls.append((args, kwargs, self._options))

    task = FakeDjangoTask()

    with scope(policy=AllowAll(), executor=django_tasks_executor):
        enqueue(
            task,
            "arg1",
            _dispatch_options={"priority": 100, "queue_name": "critical"},
            user_id=123,
        )

    assert len(using_calls) == 1
    assert using_calls[0] == {"priority": 100, "queue_name": "critical"}

    assert len(enqueue_calls) == 1
    args, kwargs, options = enqueue_calls[0]
    assert args == ("arg1",)
    assert kwargs == {"user_id": 123}
    assert options == {"priority": 100, "queue_name": "critical"}


def test_integration_no_options_uses_direct_enqueue():
    """Test that without dispatch_options, .enqueue() is called directly."""
    from airlock import scope, enqueue, AllowAll
    from airlock.integrations.executors.django_tasks import django_tasks_executor

    enqueue_calls = []
    using_calls = []

    class FakeDjangoTask:
        def using(self, **options):
            using_calls.append(options)
            return self

        def enqueue(self, *args, **kwargs):
            enqueue_calls.append((args, kwargs))

    task = FakeDjangoTask()

    with scope(policy=AllowAll(), executor=django_tasks_executor):
        enqueue(task, "arg", key="val")

    # .using() should NOT be called
    assert len(using_calls) == 0
    # .enqueue() should be called directly
    assert len(enqueue_calls) == 1
    assert enqueue_calls[0] == (("arg",), {"key": "val"})


def test_integration_plain_callable_fallback():
    """Test plain callables work without Django tasks framework."""
    from airlock import scope, enqueue, AllowAll
    from airlock.integrations.executors.django_tasks import django_tasks_executor

    calls = []

    def plain_function(x, y=None):
        calls.append((x, y))

    with scope(policy=AllowAll(), executor=django_tasks_executor):
        enqueue(plain_function, 42, y="value")

    assert len(calls) == 1
    assert calls[0] == (42, "value")
