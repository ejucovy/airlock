"""Tests for core enqueue functionality."""

import pytest

try:
    import celery
    HAS_CELERY = True
except ImportError:
    HAS_CELERY = False

import airlock
from airlock import enqueue, PolicyEnqueueError, NoScopeError, PolicyViolation, scope, AllowAll, AssertNoEffects
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

    @pytest.mark.skipif(not HAS_CELERY, reason="celery not installed")
    def test_dispatch_options_passed_to_apply_async(self):
        """Test that dispatch_options are passed to apply_async."""
        from airlock.integrations.executors.celery import celery_executor

        apply_async_calls = []

        class FakeCeleryTask:
            name = "test.task"

            def apply_async(self, args=None, kwargs=None, **options):
                apply_async_calls.append((args, kwargs, options))

        task = FakeCeleryTask()

        with scope(policy=AllowAll(), executor=celery_executor):
            enqueue(
                task,
                "arg1",
                _dispatch_options={"countdown": 30, "queue": "high"},
                user_id=123,
            )

        # Verify apply_async was called with options
        assert len(apply_async_calls) == 1
        args, kwargs, options = apply_async_calls[0]
        assert args == ("arg1",)
        assert kwargs == {"user_id": 123}
        assert options == {"countdown": 30, "queue": "high"}

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

    @pytest.mark.skipif(not HAS_CELERY, reason="celery not installed")
    def test_dispatch_options_prefers_apply_async_over_delay(self):
        """Test that apply_async is used when dispatch_options are present."""
        from airlock.integrations.executors.celery import celery_executor

        delay_calls = []
        apply_async_calls = []

        class FakeTask:
            name = "test.task"

            def delay(self, *args, **kwargs):
                delay_calls.append((args, kwargs))

            def apply_async(self, args=None, kwargs=None, **options):
                apply_async_calls.append((args, kwargs, options))

        task = FakeTask()

        with scope(policy=AllowAll(), executor=celery_executor):
            enqueue(task, "arg", _dispatch_options={"countdown": 10})

        # apply_async should be used, not delay
        assert len(delay_calls) == 0
        assert len(apply_async_calls) == 1

    @pytest.mark.skipif(not HAS_CELERY, reason="celery not installed")
    def test_delay_used_without_dispatch_options(self):
        """Test that delay is used when no dispatch_options are present."""
        from airlock.integrations.executors.celery import celery_executor

        delay_calls = []
        apply_async_calls = []

        class FakeTask:
            name = "test.task"

            def delay(self, *args, **kwargs):
                delay_calls.append((args, kwargs))

            def apply_async(self, args=None, kwargs=None, **options):
                apply_async_calls.append((args, kwargs, options))

        task = FakeTask()

        with scope(policy=AllowAll(), executor=celery_executor):
            enqueue(task, "arg", key="val")

        # delay should be used when no options
        assert len(delay_calls) == 1
        assert len(apply_async_calls) == 0
