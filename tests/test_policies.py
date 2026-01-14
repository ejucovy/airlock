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

    def test_repr(self):
        """Test AllowAll string representation."""
        policy = AllowAll()
        assert repr(policy) == "AllowAll()"


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

    def test_repr(self):
        """Test DropAll string representation."""
        policy = DropAll()
        assert repr(policy) == "DropAll()"


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

    def test_repr(self):
        """Test AssertNoEffects string representation."""
        policy = AssertNoEffects()
        assert repr(policy) == "AssertNoEffects()"


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

    def test_repr(self):
        """Test BlockTasks string representation."""
        policy = BlockTasks({"task_a", "task_b"})
        repr_str = repr(policy)
        assert "BlockTasks" in repr_str
        assert "task_a" in repr_str
        assert "task_b" in repr_str

    def test_repr_with_raise_on_enqueue(self):
        """Test BlockTasks repr includes raise_on_enqueue flag."""
        policy = BlockTasks({"task_a"}, raise_on_enqueue=True)
        repr_str = repr(policy)
        assert "BlockTasks" in repr_str
        assert "raise_on_enqueue=True" in repr_str


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

    def test_repr(self):
        """Test LogOnFlush string representation."""
        policy = LogOnFlush()
        repr_str = repr(policy)
        assert "LogOnFlush" in repr_str
        assert "airlock" in repr_str  # Default logger name

    def test_repr_custom_logger(self):
        """Test LogOnFlush repr with custom logger."""
        logger = logging.getLogger("custom.logger")
        policy = LogOnFlush(logger=logger)
        repr_str = repr(policy)
        assert "LogOnFlush" in repr_str
        assert "custom.logger" in repr_str


