"""Tests for core enqueue functionality."""

import pytest

import airlock
from airlock import enqueue, PolicyEnqueueError, NoScopeError, PolicyViolation, scope, scoped, AllowAll, AssertNoEffects, DropAll
from airlock import _in_policy


# Test tasks
def my_task(*args, **kwargs):
    pass


def task_a():
    pass


def task_b():
    pass


def task_c():
    pass


def email_send(user_id=None):
    pass


def notification_push(message=None):
    pass


def process_background(entity_id=None):
    pass


def email_confirmation():
    pass


class TestEnqueue:
    """Tests for the enqueue function."""

    def test_enqueue_buffers_in_scope(self):
        """Test that enqueue buffers intents in active scope."""
        with scope(policy=AllowAll()) as s:
            enqueue(my_task, "arg1", key="value")

        assert len(s.intents) == 1
        intent = s.intents[0]
        assert intent.task is my_task
        assert intent.args == ("arg1",)
        assert intent.kwargs == {"key": "value"}

    def test_enqueue_multiple_tasks(self):
        """Test enqueueing multiple tasks."""
        with scope(policy=AllowAll()) as s:
            enqueue(task_a)
            enqueue(task_b)
            enqueue(task_c)

        assert len(s.intents) == 3
        assert [i.task for i in s.intents] == [task_a, task_b, task_c]

    def test_enqueue_raises_without_scope(self):
        """Test that enqueue raises without an active scope."""
        with pytest.raises(NoScopeError) as exc_info:
            enqueue(my_task)

        assert "without an active airlock.scope()" in str(exc_info.value)

    def test_enqueue_raises_from_policy(self):
        """Test that enqueue from a policy raises an error."""
        # Simulate being in a policy callback
        token = _in_policy.set(True)

        try:
            with pytest.raises(PolicyEnqueueError) as exc_info:
                enqueue(my_task)

            assert "policy callback" in str(exc_info.value)
        finally:
            _in_policy.reset(token)

    def test_enqueue_origin_defaults_to_none(self):
        """Test that origin defaults to None when not specified."""
        with scope(policy=AllowAll()) as s:
            enqueue(my_task)

        intent = s.intents[0]
        # Origin is NOT auto-detected - it must be set explicitly by integrations
        assert intent.origin is None

    def test_enqueue_origin_can_be_set_explicitly(self):
        """Test that origin can be explicitly set."""
        with scope(policy=AllowAll()) as s:
            enqueue(my_task, _origin="custom:origin")

        intent = s.intents[0]
        assert intent.origin == "custom:origin"

    def test_enqueue_respects_policy_on_enqueue(self):
        """Test that policy.on_enqueue is called."""
        with pytest.raises(PolicyViolation):
            with scope(policy=AssertNoEffects()):
                enqueue(my_task)


class TestEnqueueIntegration:
    """Integration tests for enqueue with scope."""

    def test_enqueue_and_dispatch(self):
        """Test the full cycle: enqueue -> flush -> dispatch."""
        # Track calls to verify dispatch
        calls = []

        def tracked_task(*args, **kwargs):
            calls.append((args, kwargs))

        with scope(policy=AllowAll()):
            enqueue(tracked_task, user_id=123)
            enqueue(tracked_task, message="Hello")

        # Plain callables are called directly on flush
        assert len(calls) == 2

    def test_nested_scopes_captured_by_default(self):
        """Test that nested scopes are captured by default (safe default)."""
        outer_calls = []
        inner_calls = []

        def outer_task():
            outer_calls.append(1)

        def inner_task():
            inner_calls.append(1)

        with scope(policy=AllowAll()):
            enqueue(outer_task)

            with scope(policy=AllowAll()):
                enqueue(inner_task)

            # Inner task captured, hasn't executed yet
            assert len(inner_calls) == 0
            enqueue(outer_task)

        # All tasks flush together
        assert len(outer_calls) == 2
        assert len(inner_calls) == 1

    def test_domain_code_pattern(self):
        """Test the intended domain code pattern."""
        calls = []

        def process_background(entity_id):
            calls.append(("process", entity_id))

        def email_confirmation():
            calls.append(("email",))

        # This simulates domain code that doesn't know about scopes
        def model_method():
            airlock.enqueue(process_background, 456)

        def view():
            model_method()
            airlock.enqueue(email_confirmation)

        # This simulates the request handler/middleware
        with airlock.scope(policy=airlock.AllowAll()):
            view()

        assert len(calls) == 2
        assert calls[0] == ("process", 456)
        assert calls[1] == ("email",)


class TestDispatchOptions:
    """Tests for _dispatch_options parameter."""

    def test_enqueue_with_dispatch_options(self):
        """Test that dispatch_options are captured on the intent."""
        with scope(policy=AllowAll()) as s:
            enqueue(
                my_task,
                "arg1",
                _dispatch_options={"countdown": 60, "queue": "emails"},
                key="value",
            )

        assert len(s.intents) == 1
        intent = s.intents[0]
        assert intent.dispatch_options == {"countdown": 60, "queue": "emails"}
        assert intent.args == ("arg1",)
        assert intent.kwargs == {"key": "value"}

    def test_enqueue_without_dispatch_options(self):
        """Test that dispatch_options is None when not provided."""
        with scope(policy=AllowAll()) as s:
            enqueue(my_task, "arg1")

        intent = s.intents[0]
        assert intent.dispatch_options is None

    def test_dispatch_options_ignored_for_plain_callable(self):
        """Test that dispatch_options are silently ignored for plain callables."""
        calls = []

        def plain_func(*args, **kwargs):
            calls.append((args, kwargs))

        with scope(policy=AllowAll()):
            enqueue(
                plain_func,
                "arg1",
                _dispatch_options={"countdown": 60},  # Should be ignored
                key="value",
            )

        # Plain callable was called normally
        assert len(calls) == 1
        assert calls[0] == (("arg1",), {"key": "value"})


class TestScopedDecorator:
    """Tests for the @scoped() decorator."""

    def test_scoped_creates_scope(self):
        """Test that @scoped creates a scope for the function."""
        calls = []

        def tracked_task():
            calls.append(1)

        @scoped()
        def my_func():
            enqueue(tracked_task)

        my_func()

        # Task should have been dispatched
        assert len(calls) == 1

    def test_scoped_flushes_on_success(self):
        """Test that @scoped flushes on successful return."""
        calls = []

        def tracked_task(value):
            calls.append(value)

        @scoped()
        def my_func():
            enqueue(tracked_task, "hello")
            return "result"

        result = my_func()

        assert result == "result"
        assert calls == ["hello"]

    def test_scoped_discards_on_exception(self):
        """Test that @scoped discards on exception."""
        calls = []

        def tracked_task():
            calls.append(1)

        @scoped()
        def my_func():
            enqueue(tracked_task)
            raise ValueError("oops")

        with pytest.raises(ValueError):
            my_func()

        # Task should NOT have been dispatched
        assert len(calls) == 0

    def test_scoped_with_policy(self):
        """Test that @scoped accepts a policy."""
        calls = []

        def tracked_task():
            calls.append(1)

        @scoped(policy=DropAll())
        def my_func():
            enqueue(tracked_task)

        my_func()

        # Task should NOT have been dispatched (DropAll policy)
        assert len(calls) == 0

    def test_scoped_with_args_and_kwargs(self):
        """Test that @scoped preserves function arguments."""
        @scoped()
        def my_func(a, b, c=None):
            return (a, b, c)

        result = my_func(1, 2, c=3)
        assert result == (1, 2, 3)

    def test_scoped_preserves_function_metadata(self):
        """Test that @scoped preserves __name__ and __doc__."""
        @scoped()
        def my_documented_func():
            """This is my docstring."""
            pass

        assert my_documented_func.__name__ == "my_documented_func"
        assert my_documented_func.__doc__ == "This is my docstring."

    def test_scoped_each_call_gets_fresh_scope(self):
        """Test that each call to a @scoped function gets its own scope."""
        calls = []

        def tracked_task(call_id):
            calls.append(call_id)

        @scoped()
        def my_func(call_id):
            enqueue(tracked_task, call_id)

        my_func(1)
        my_func(2)
        my_func(3)

        # Each call should have flushed independently
        assert calls == [1, 2, 3]

    def test_scoped_works_with_celery_style_stacking(self):
        """Test that @scoped works when stacked with other decorators."""
        calls = []

        def tracked_task():
            calls.append(1)

        # Simulate Celery's @app.task decorator
        def fake_celery_task(func):
            def wrapper(*args, **kwargs):
                return func(*args, **kwargs)
            wrapper.__name__ = func.__name__
            return wrapper

        @fake_celery_task
        @scoped()
        def my_celery_task():
            enqueue(tracked_task)

        my_celery_task()

        assert len(calls) == 1

    def test_scoped_no_scope_leak_between_calls(self):
        """Test that scopes don't leak between sequential calls."""
        from airlock import get_current_scope

        @scoped()
        def my_func():
            assert get_current_scope() is not None

        # Before: no scope
        assert get_current_scope() is None

        my_func()

        # After: no scope
        assert get_current_scope() is None

        my_func()

        # Still no scope
        assert get_current_scope() is None
