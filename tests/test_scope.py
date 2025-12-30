"""Tests for airlock.scope."""

import pytest

import airlock
from airlock import Intent, scope, Scope, AllowAll, DropAll, get_current_scope, ScopeStateError


# Test task
def test_task():
    pass


def task_a():
    pass


def task_b():
    pass


def task_c():
    pass


def make_intent(task=None) -> Intent:
    """Helper to create a test intent."""
    if task is None:
        task = test_task
    return Intent(task=task, args=(), kwargs={})


class TestScope:
    """Tests for the Scope class."""

    def test_add_intent(self):
        """Test adding intents to a scope."""
        s = Scope(policy=AllowAll())

        intent = make_intent()
        s._add(intent)

        assert len(s.intents) == 1
        assert s.intents[0] == intent

    def test_add_multiple_intents(self):
        """Test adding multiple intents."""
        s = Scope(policy=AllowAll())

        s._add(make_intent(task_a))
        s._add(make_intent(task_b))
        s._add(make_intent(task_c))

        assert len(s.intents) == 3
        assert [i.task for i in s.intents] == [task_a, task_b, task_c]

    def test_flush_returns_dispatched_intents(self):
        """Test that flush returns the dispatched intents."""
        s = Scope(policy=AllowAll())
        s._add(make_intent(task_a))
        s._add(make_intent(task_b))

        result = s.flush()

        assert len(result) == 2

    def test_flush_marks_scope_as_flushed(self):
        """Test that flush sets the is_flushed flag."""
        s = Scope(policy=AllowAll())

        assert not s.is_flushed
        s.flush()
        assert s.is_flushed

    def test_cannot_flush_twice(self):
        """Test that flushing twice raises an error."""
        s = Scope(policy=AllowAll())
        s.flush()

        with pytest.raises(ScopeStateError, match="already been flushed"):
            s.flush()

    def test_cannot_add_after_flush(self):
        """Test that adding after flush raises an error."""
        s = Scope(policy=AllowAll())
        s.flush()

        with pytest.raises(ScopeStateError, match="flushed"):
            s._add(make_intent())

    def test_discard_returns_discarded_intents(self):
        """Test that discard returns the discarded intents."""
        s = Scope(policy=AllowAll())
        s._add(make_intent(task_a))
        s._add(make_intent(task_b))

        result = s.discard()

        assert len(result) == 2

    def test_discard_marks_scope_as_discarded(self):
        """Test that discard sets the is_discarded flag."""
        s = Scope(policy=AllowAll())

        assert not s.is_discarded
        s.discard()
        assert s.is_discarded

    def test_cannot_discard_after_flush(self):
        """Test that discarding after flush raises an error."""
        s = Scope(policy=AllowAll())
        s.flush()

        with pytest.raises(ScopeStateError, match="flushed"):
            s.discard()

    def test_cannot_flush_after_discard(self):
        """Test that flushing after discard raises an error."""
        s = Scope(policy=AllowAll())
        s.discard()

        with pytest.raises(ScopeStateError, match="discarded"):
            s.flush()

    def test_policy_on_enqueue_is_called(self):
        """Test that policy.on_enqueue is called when adding."""

        class TrackingPolicy:
            def __init__(self):
                self.enqueued = []

            def on_enqueue(self, intent):
                self.enqueued.append(intent)

            def on_flush(self, intents):
                return intents

        policy = TrackingPolicy()
        s = Scope(policy=policy)
        intent = make_intent()

        s._add(intent)

        assert len(policy.enqueued) == 1
        assert policy.enqueued[0] == intent

    def test_policy_on_flush_filters_intents(self):
        """Test that policy.on_flush can filter intents."""
        s = Scope(policy=DropAll())
        s._add(make_intent(task_a))
        s._add(make_intent(task_b))

        result = s.flush()

        assert result == []

    def test_manual_scope_lifecycle(self):
        """Test low-level Scope API for integration authors.

        Manually created Scope (not via context manager) can be
        flushed directly. This is the intended API for integrations
        like DjangoScope that need custom lifecycle control.
        """
        calls = []

        def tracked():
            calls.append(1)

        # Manual lifecycle - NOT using context manager
        s = Scope(policy=AllowAll())
        assert not s.is_flushed
        assert not s.is_discarded

        s._add(make_intent(tracked))
        assert len(s.intents) == 1

        # Flush dispatches
        result = s.flush()
        assert len(calls) == 1
        assert s.is_flushed
        assert len(result) == 1

    def test_manual_scope_discard(self):
        """Test low-level discard for integration authors."""
        calls = []

        def tracked():
            calls.append(1)

        s = Scope(policy=AllowAll())
        s._add(make_intent(tracked))

        # Discard does not dispatch
        discarded = s.discard()
        assert len(calls) == 0
        assert s.is_discarded
        assert len(discarded) == 1


class TestScopeImperativeAPI:
    """Tests for the imperative enter()/exit() API."""

    def test_enter_activates_scope(self):
        """Test that enter() makes scope active."""
        s = Scope(policy=AllowAll())
        assert not s.is_active
        assert get_current_scope() is None

        s.enter()
        assert s.is_active
        assert get_current_scope() is s

        s.exit()
        assert not s.is_active
        assert get_current_scope() is None

    def test_enter_returns_self(self):
        """Test that enter() returns self for chaining."""
        s = Scope(policy=AllowAll())
        result = s.enter()
        assert result is s
        s.exit()

    def test_enter_twice_raises(self):
        """Test that entering an already-active scope raises."""
        s = Scope(policy=AllowAll())
        s.enter()

        with pytest.raises(ScopeStateError, match="already active"):
            s.enter()

        s.exit()

    def test_exit_without_enter_raises(self):
        """Test that exiting a non-active scope raises."""
        s = Scope(policy=AllowAll())

        with pytest.raises(ScopeStateError, match="not active"):
            s.exit()

    def test_imperative_flush_pattern(self):
        """Test the full imperative pattern for integrations."""
        calls = []

        def tracked():
            calls.append(1)

        s = Scope(policy=AllowAll())
        s.enter()

        # Enqueue works when scope is active
        import airlock
        airlock.enqueue(tracked)

        s.exit()

        # Flush after exit
        s.flush()
        assert len(calls) == 1

    def test_imperative_discard_pattern(self):
        """Test the imperative discard pattern."""
        calls = []

        def tracked():
            calls.append(1)

        s = Scope(policy=AllowAll())
        s.enter()

        import airlock
        airlock.enqueue(tracked)

        s.exit()

        # Discard after exit
        s.discard()
        assert len(calls) == 0

    def test_nested_enter_exit(self):
        """Test nested imperative scopes."""
        outer = Scope(policy=AllowAll())
        inner = Scope(policy=AllowAll())

        outer.enter()
        assert get_current_scope() is outer

        inner.enter()
        assert get_current_scope() is inner

        inner.exit()
        assert get_current_scope() is outer

        outer.exit()
        assert get_current_scope() is None

    def test_should_flush_default(self):
        """Test default should_flush behavior."""
        s = Scope(policy=AllowAll())

        # Success case
        assert s.should_flush(None) is True

        # Error case
        assert s.should_flush(ValueError("test")) is False

    def test_should_flush_custom(self):
        """Test custom should_flush via subclass."""
        class AlwaysFlush(Scope):
            def should_flush(self, error):
                return True

        s = AlwaysFlush(policy=AllowAll())
        assert s.should_flush(ValueError("test")) is True

    def test_should_flush_with_intent_inspection(self):
        """Test should_flush can inspect scope state."""
        class ConditionalScope(Scope):
            def should_flush(self, error):
                if error:
                    return False
                # Only flush if we have intents
                return len(self.intents) > 0

        s = ConditionalScope(policy=AllowAll())
        s.enter()

        # No intents - should not flush
        s.exit()
        assert s.should_flush(None) is False

        # Reset and add intent
        s2 = ConditionalScope(policy=AllowAll())
        s2.enter()
        import airlock
        airlock.enqueue(lambda: None)
        s2.exit()
        assert s2.should_flush(None) is True


class TestScopeContextManager:
    """Tests for the scope context manager."""

    def test_scope_is_active_inside(self):
        """Test that get_current_scope returns the scope inside."""
        with scope(policy=AllowAll()) as s:
            assert get_current_scope() is s

    def test_scope_is_not_active_outside(self):
        """Test that get_current_scope returns None outside."""
        assert get_current_scope() is None

        with scope(policy=AllowAll()):
            pass

        assert get_current_scope() is None

    def test_nested_scopes(self):
        """Test nested scope handling."""
        with scope(policy=AllowAll()) as outer:
            assert get_current_scope() is outer

            with scope(policy=DropAll()) as inner:
                assert get_current_scope() is inner
                assert get_current_scope() is not outer

            assert get_current_scope() is outer

        assert get_current_scope() is None

    def test_flushes_on_normal_exit(self):
        """Test that scope flushes on normal exit."""
        calls = []

        def tracked():
            calls.append(1)

        with scope(policy=AllowAll()) as s:
            s._add(make_intent(tracked))

        assert len(calls) == 1

    def test_discards_on_exception(self):
        """Test that scope discards on exception."""
        calls = []

        def tracked():
            calls.append(1)

        with pytest.raises(ValueError):
            with scope(policy=AllowAll()) as s:
                s._add(make_intent(tracked))
                raise ValueError("Something went wrong")

        assert len(calls) == 0

    def test_flush_on_error_with_custom_scope(self):
        """Test that scope can flush on exception with custom should_flush."""
        calls = []

        def tracked():
            calls.append(1)

        class AlwaysFlushScope(Scope):
            def should_flush(self, error):
                return True  # Flush even on error

        with pytest.raises(ValueError):
            with scope(policy=AllowAll(), _cls=AlwaysFlushScope) as s:
                s._add(make_intent(tracked))
                raise ValueError("Something went wrong")

        assert len(calls) == 1

    def test_never_flush_with_custom_scope(self):
        """Test that scope doesn't flush with custom should_flush returning False."""
        calls = []

        def tracked():
            calls.append(1)

        class NeverFlushScope(Scope):
            def should_flush(self, error):
                return False  # Never flush

        with scope(policy=AllowAll(), _cls=NeverFlushScope) as s:
            s._add(make_intent(tracked))

        assert len(calls) == 0

    def test_manual_flush_inside_scope_raises(self):
        """Test that manual flush inside the scope raises ScopeStateError."""
        calls = []

        def tracked():
            calls.append(1)

        with pytest.raises(ScopeStateError, match="Cannot flush.*while scope is still active"):
            with scope(policy=AllowAll()) as s:
                s._add(make_intent(tracked))
                s.flush()  # Should raise

        # Intent never dispatched
        assert len(calls) == 0

    def test_manual_discard_inside_scope_raises(self):
        """Test that manual discard inside the scope raises ScopeStateError."""
        calls = []

        def tracked():
            calls.append(1)

        with pytest.raises(ScopeStateError, match="Cannot discard.*while scope is still active"):
            with scope(policy=AllowAll()) as s:
                s._add(make_intent(tracked))
                s.discard()  # Should raise

        # Intent never dispatched
        assert len(calls) == 0

    def test_default_policy_is_allow_all(self):
        """Test that default policy allows all intents."""
        calls = []

        def tracked():
            calls.append(1)

        with scope() as s:
            s._add(make_intent(tracked))

        assert len(calls) == 1
