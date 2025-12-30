"""Tests for policies."""

import logging
import pytest

from airlock import (
    Intent,
    AllowAll,
    DropAll,
    AssertNoEffects,
    BlockTasks,
    LogOnFlush,
    CompositePolicy,
    PolicyViolation,
)


def dummy_task():
    pass


def task_a():
    pass


def task_b():
    pass


def allowed_task():
    pass


def blocked_task():
    pass


class FakeTask:
    """A fake task with a .name attribute like Celery tasks."""

    def __init__(self, name):
        self.name = name

    def __call__(self):
        pass


def make_intent(task=None, name=None) -> Intent:
    """Helper to create a test intent."""
    if task is None:
        if name:
            task = FakeTask(name)
        else:
            task = dummy_task
    return Intent(task=task, args=(), kwargs={})


class TestAllowAll:
    """Tests for AllowAll policy."""

    def test_allows_enqueue(self):
        """Test that on_enqueue doesn't raise."""
        policy = AllowAll()
        intent = make_intent()

        # Should not raise
        policy.on_enqueue(intent)

    def test_allows_all_intents(self):
        """Test that allows returns True for all intents."""
        policy = AllowAll()
        intents = [make_intent(task_a), make_intent(task_b), make_intent(dummy_task)]

        for intent in intents:
            assert policy.allows(intent) is True


class TestDropAll:
    """Tests for DropAll policy."""

    def test_allows_enqueue(self):
        """Test that on_enqueue doesn't raise (drops at flush)."""
        policy = DropAll()
        intent = make_intent()

        # Should not raise
        policy.on_enqueue(intent)

    def test_denies_all_intents(self):
        """Test that allows returns False for all intents."""
        policy = DropAll()
        intents = [make_intent(task_a), make_intent(task_b), make_intent(dummy_task)]

        for intent in intents:
            assert policy.allows(intent) is False


class TestAssertNoEffects:
    """Tests for AssertNoEffects policy."""

    def test_raises_on_enqueue(self):
        """Test that on_enqueue raises PolicyViolation."""
        policy = AssertNoEffects()
        intent = make_intent()

        with pytest.raises(PolicyViolation) as exc_info:
            policy.on_enqueue(intent)

        assert "Unexpected side effect" in str(exc_info.value)

    def test_allows_returns_false(self):
        """Test that allows returns False (unreachable in practice)."""
        policy = AssertNoEffects()
        intent = make_intent()

        # on_enqueue always raises, so allows is never called in practice
        # But it must return False to satisfy the Protocol
        assert policy.allows(intent) is False


class TestBlockTasks:
    """Tests for BlockTasks policy."""

    def test_allows_non_blocked_enqueue(self):
        """Test that non-blocked tasks pass on_enqueue."""
        policy = BlockTasks({"blocked_task"})
        intent = make_intent(name="allowed_task")

        # Should not raise
        policy.on_enqueue(intent)

    def test_allows_blocked_enqueue_by_default(self):
        """Test that blocked tasks pass on_enqueue by default."""
        policy = BlockTasks({"blocked_task"})
        intent = make_intent(name="blocked_task")

        # Should not raise (drops at flush by default)
        policy.on_enqueue(intent)

    def test_raises_on_blocked_enqueue_when_configured(self):
        """Test that blocked tasks raise on_enqueue when configured."""
        policy = BlockTasks({"blocked_task"}, raise_on_enqueue=True)
        intent = make_intent(name="blocked_task")

        with pytest.raises(PolicyViolation) as exc_info:
            policy.on_enqueue(intent)

        assert "blocked_task" in str(exc_info.value)
        assert "blocked" in str(exc_info.value)

    def test_allows_non_blocked_intents(self):
        """Test that non-blocked tasks are allowed."""
        policy = BlockTasks({"blocked_a", "blocked_b"})

        assert policy.allows(make_intent(name="allowed")) is True
        assert policy.allows(make_intent(name="also_allowed")) is True

    def test_denies_blocked_intents(self):
        """Test that blocked tasks are denied."""
        policy = BlockTasks({"blocked_a", "blocked_b"})

        assert policy.allows(make_intent(name="blocked_a")) is False
        assert policy.allows(make_intent(name="blocked_b")) is False


class TestLogOnFlush:
    """Tests for LogOnFlush policy."""

    def test_allows_enqueue(self):
        """Test that on_enqueue doesn't raise."""
        policy = LogOnFlush()
        intent = make_intent()

        # Should not raise
        policy.on_enqueue(intent)

    def test_allows_and_returns_true(self):
        """Test that allows returns True for all intents."""
        policy = LogOnFlush()
        intents = [make_intent(task_a), make_intent(task_b)]

        for intent in intents:
            assert policy.allows(intent) is True

    def test_logs_on_allows(self, caplog):
        """Test that allows logs the intent."""
        logger = logging.getLogger("airlock")
        policy = LogOnFlush(logger=logger)
        intent = make_intent(name="task_a")

        with caplog.at_level(logging.INFO, logger="airlock"):
            policy.allows(intent)

        assert "task_a" in caplog.text


class TestCompositePolicy:
    """Tests for CompositePolicy."""

    def test_calls_all_on_enqueue(self):
        """Test that on_enqueue calls all policies."""
        calls = []

        class TrackingPolicy:
            def __init__(self, name):
                self.name = name

            def on_enqueue(self, intent):
                calls.append(self.name)

            def allows(self, intent):
                return True

        policy = CompositePolicy(
            TrackingPolicy("first"),
            TrackingPolicy("second"),
            TrackingPolicy("third"),
        )
        intent = make_intent()

        policy.on_enqueue(intent)

        assert calls == ["first", "second", "third"]

    def test_allows_requires_all_policies(self):
        """Test that allows returns True only if all policies allow."""

        class AllowPolicy:
            def on_enqueue(self, intent):
                pass

            def allows(self, intent):
                return True

        class DenyPolicy:
            def on_enqueue(self, intent):
                pass

            def allows(self, intent):
                return False

        # All allow -> True
        policy = CompositePolicy(AllowPolicy(), AllowPolicy())
        assert policy.allows(make_intent()) is True

        # Any deny -> False
        policy = CompositePolicy(AllowPolicy(), DenyPolicy())
        assert policy.allows(make_intent()) is False

        # First denies -> False (short-circuits)
        policy = CompositePolicy(DenyPolicy(), AllowPolicy())
        assert policy.allows(make_intent()) is False

    def test_stops_on_first_exception_enqueue(self):
        """Test that on_enqueue stops on first exception."""

        class RaisingPolicy:
            def on_enqueue(self, intent):
                raise ValueError("Stop!")

            def allows(self, intent):
                return True

        class TrackingPolicy:
            def __init__(self):
                self.called = False

            def on_enqueue(self, intent):
                self.called = True

            def allows(self, intent):
                return True

        tracker = TrackingPolicy()
        policy = CompositePolicy(RaisingPolicy(), tracker)

        with pytest.raises(ValueError):
            policy.on_enqueue(make_intent())

        assert not tracker.called

    def test_combines_logging_and_blocking(self):
        """Test combining LogOnFlush with BlockTasks."""
        policy = CompositePolicy(
            LogOnFlush(),
            BlockTasks({"blocked_task"}),
        )

        # Allowed intent
        assert policy.allows(make_intent(name="allowed")) is True

        # Blocked intent
        assert policy.allows(make_intent(name="blocked_task")) is False
