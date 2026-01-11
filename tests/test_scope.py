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

    def test_cannot_discard_twice(self):
        """Test that discarding twice raises an error."""
        s = Scope(policy=AllowAll())
        s.discard()

        with pytest.raises(ScopeStateError, match="already been discarded"):
            s.discard()

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

    def test_scope_subclass_that_flushes_in_exit(self):
        """Test that context manager handles scope already flushed in exit()."""
        calls = []

        def tracked():
            calls.append(1)

        class EagerFlushScope(Scope):
            """A scope that flushes immediately on exit."""
            def exit(self):
                super().exit()
                self.flush()

        with scope(policy=AllowAll(), _cls=EagerFlushScope) as s:
            s._add(make_intent(tracked))

        # Should have flushed once (in exit), not twice
        assert len(calls) == 1
        assert s.is_flushed


class TestNestedScopeCapture:
    """Tests for nested scope capture behavior via before_descendant_flushes."""

    def test_default_captures_nested_flush(self):
        """Test that by default, nested scopes are captured (safe default)."""
        outer_calls = []
        inner_calls = []

        def outer_task():
            outer_calls.append(1)

        def inner_task():
            inner_calls.append(1)

        with scope(policy=AllowAll()) as outer:
            airlock.enqueue(outer_task)

            with scope(policy=AllowAll()) as inner:
                airlock.enqueue(inner_task)

            # Default: inner's intents captured by outer
            assert len(inner_calls) == 0
            assert len(outer_calls) == 0

        # Both flush together when outer exits
        assert len(inner_calls) == 1
        assert len(outer_calls) == 1

    def test_independent_scope_allows_nested_flush(self):
        """Test that IndependentScope allows nested scopes to flush independently."""
        outer_calls = []
        inner_calls = []

        def outer_task():
            outer_calls.append(1)

        def inner_task():
            inner_calls.append(1)

        class IndependentScope(Scope):
            def before_descendant_flushes(self, exiting_scope, intents):
                return intents  # Allow independent flush

        with scope(policy=AllowAll(), _cls=IndependentScope) as outer:
            airlock.enqueue(outer_task)

            with scope(policy=AllowAll()) as inner:
                airlock.enqueue(inner_task)

            # Inner flushed independently
            assert len(inner_calls) == 1
            assert len(outer_calls) == 0

        # Outer flushes its own
        assert len(outer_calls) == 1

    def test_selective_capture(self):
        """Test that scope can selectively capture specific intents."""
        calls = []

        def safe_task():
            calls.append('safe')

        def dangerous_task():
            calls.append('dangerous')

        class SmartScope(Scope):
            def before_descendant_flushes(self, exiting_scope, intents):
                # Allow safe tasks, capture dangerous ones
                return [i for i in intents if 'dangerous' not in i.name]

        with scope(policy=AllowAll(), _cls=SmartScope) as outer:
            with scope(policy=AllowAll()) as inner:
                airlock.enqueue(safe_task)
                airlock.enqueue(dangerous_task)

            # Safe task flushed immediately, dangerous was captured
            assert 'safe' in calls
            assert 'dangerous' not in calls

        # Dangerous task flushes when outer exits
        assert 'dangerous' in calls

    def test_multi_level_nesting_walks_full_chain(self):
        """Test that intents walk up through multiple levels."""
        calls = []

        def task():
            calls.append(1)

        class CapturingScope(Scope):
            def before_descendant_flushes(self, exiting_scope, intents):
                return []  # Capture everything

        with scope(policy=AllowAll(), _cls=CapturingScope) as outer:
            with scope(policy=AllowAll()) as middle:
                with scope(policy=AllowAll()) as inner:
                    airlock.enqueue(task)

                # Innermost tried to flush, middle allowed, but outer captured
                assert len(calls) == 0

            # Middle tried to flush its own buffer (empty), nothing happens
            assert len(calls) == 0

        # Outer flushes captured intent
        assert len(calls) == 1

    def test_provenance_tracking_own_vs_captured(self):
        """Test that scopes track which intents are their own vs captured."""

        def own_task():
            pass

        def captured_task():
            pass

        class CapturingScope(Scope):
            def before_descendant_flushes(self, exiting_scope, intents):
                return []

        with scope(policy=AllowAll(), _cls=CapturingScope) as outer:
            airlock.enqueue(own_task)

            with scope(policy=AllowAll()) as inner:
                airlock.enqueue(captured_task)

            # Check provenance
            assert len(outer.intents) == 2  # Total
            assert len(outer.own_intents) == 1  # Own
            assert len(outer.captured_intents) == 1  # Captured

            assert outer.own_intents[0].task == own_task
            assert outer.captured_intents[0].task == captured_task

    def test_captured_intents_respect_outer_policy(self):
        """Test that captured intents are subject to outer scope's policy."""
        calls = []

        def allowed_task():
            calls.append('allowed')

        def blocked_task():
            calls.append('blocked')

        class CapturingScope(Scope):
            def before_descendant_flushes(self, exiting_scope, intents):
                return []

        # Custom policy that blocks specific task by identity
        class BlockSpecificTask:
            def __init__(self, blocked_task_obj):
                self.blocked_task = blocked_task_obj

            def on_enqueue(self, intent):
                pass

            def allows(self, intent):
                return intent.task is not self.blocked_task

        # Outer scope blocks 'blocked_task'
        with scope(
            policy=BlockSpecificTask(blocked_task),
            _cls=CapturingScope
        ) as outer:
            with scope(policy=AllowAll()) as inner:
                airlock.enqueue(allowed_task)
                airlock.enqueue(blocked_task)

            # Both captured
            assert len(calls) == 0

        # Only allowed_task flushes (blocked_task filtered by outer policy)
        assert calls == ['allowed']

    def test_nested_scope_discard_doesnt_affect_parent(self):
        """Test that nested scope discard doesn't affect parent buffer."""
        calls = []

        def outer_task():
            calls.append('outer')

        def inner_task():
            calls.append('inner')

        with scope(policy=AllowAll()) as outer:
            airlock.enqueue(outer_task)

            try:
                with scope(policy=AllowAll()) as inner:
                    airlock.enqueue(inner_task)
                    raise ValueError("test error")
            except ValueError:
                pass

            # Inner discarded its intent
            assert 'inner' not in calls

        # Outer still flushes its own intent
        assert 'outer' in calls
        assert 'inner' not in calls

    def test_chain_walk_with_mixed_capture(self):
        """Test walking a chain where some parents capture and some allow."""
        calls = []

        def task():
            calls.append(1)

        class CapturingScope(Scope):
            def before_descendant_flushes(self, exiting_scope, intents):
                return []

        class AllowingScope(Scope):
            def before_descendant_flushes(self, exiting_scope, intents):
                return intents  # Allow all

        # Outer captures, middle allows
        with scope(policy=AllowAll(), _cls=CapturingScope) as outer:
            with scope(policy=AllowAll(), _cls=AllowingScope) as middle:
                with scope(policy=AllowAll()) as inner:
                    airlock.enqueue(task)

                # Inner tries to flush
                # Middle allows it
                # Outer captures it
                assert len(calls) == 0

            # Middle has nothing of its own
            assert len(calls) == 0

        # Outer flushes captured intent
        assert len(calls) == 1

    def test_partial_capture_splits_buffer(self):
        """Test that partial capture correctly splits intents."""
        calls = []

        def task_1():
            calls.append(1)

        def task_2():
            calls.append(2)

        def task_3():
            calls.append(3)

        class SelectiveScope(Scope):
            def before_descendant_flushes(self, exiting_scope, intents):
                # Allow only task_1, capture the rest
                return [i for i in intents if '1' in i.name]

        with scope(policy=AllowAll(), _cls=SelectiveScope) as outer:
            with scope(policy=AllowAll()) as inner:
                airlock.enqueue(task_1)
                airlock.enqueue(task_2)
                airlock.enqueue(task_3)

            # Only task_1 flushed
            assert calls == [1]

        # task_2 and task_3 flush when outer exits
        assert calls == [1, 2, 3]

    def test_before_descendant_flushes_can_inspect_exiting_scope(self):
        """Test that before_descendant_flushes receives exiting scope for inspection."""
        inspected_scopes = []

        class InspectingScope(Scope):
            def before_descendant_flushes(self, exiting_scope, intents):
                inspected_scopes.append(exiting_scope)
                # Check if inner scope has certain characteristics
                if len(intents) > 2:
                    return []  # Capture if too many intents
                return intents  # Allow otherwise

        def task():
            pass

        with scope(policy=AllowAll(), _cls=InspectingScope) as outer:
            # First nested scope - few intents (allowed)
            with scope(policy=AllowAll()) as inner1:
                airlock.enqueue(task)

            assert len(inspected_scopes) == 1
            assert inspected_scopes[0] is inner1

            # Second nested scope - many intents (captured)
            with scope(policy=AllowAll()) as inner2:
                airlock.enqueue(task)
                airlock.enqueue(task)
                airlock.enqueue(task)

            assert len(inspected_scopes) == 2
            assert inspected_scopes[1] is inner2

            # inner2's intents were captured
            assert len(outer.captured_intents) == 3

    def test_before_descendant_flushes_return_none_raises_typeerror(self):
        """Test that before_descendant_flushes returning None raises TypeError."""

        class BrokenScope(Scope):
            def before_descendant_flushes(self, exiting_scope, intents):
                return None  # Bug: should return list

        def task():
            pass

        with pytest.raises(TypeError, match="before_descendant_flushes.*must return a list.*got NoneType"):
            with scope(policy=AllowAll(), _cls=BrokenScope):
                with scope(policy=AllowAll()):
                    airlock.enqueue(task)

    def test_before_descendant_flushes_return_dict_raises_typeerror(self):
        """Test that before_descendant_flushes returning wrong type raises TypeError."""

        class BrokenScope(Scope):
            def before_descendant_flushes(self, exiting_scope, intents):
                return {"intents": intents}  # Bug: should return list

        def task():
            pass

        with pytest.raises(TypeError, match="before_descendant_flushes.*must return a list.*got dict"):
            with scope(policy=AllowAll(), _cls=BrokenScope):
                with scope(policy=AllowAll()):
                    airlock.enqueue(task)

    def test_multiple_sequential_nested_scopes_all_captured(self):
        """Test that multiple sequential nested scopes don't lose intents due to ID collision."""
        calls = []

        def task1():
            calls.append(1)

        def task2():
            calls.append(2)

        def task3():
            calls.append(3)

        def task4():
            calls.append(4)

        with scope(policy=AllowAll()) as outer:
            # Create many sequential nested scopes
            # Without the fix, ID reuse could cause data loss
            with scope(policy=AllowAll()):
                airlock.enqueue(task1)

            with scope(policy=AllowAll()):
                airlock.enqueue(task2)

            with scope(policy=AllowAll()):
                airlock.enqueue(task3)

            with scope(policy=AllowAll()):
                airlock.enqueue(task4)

            # All should be captured
            assert len(calls) == 0
            assert len(outer.captured_intents) == 4
            assert len(outer.intents) == 4

        # All tasks should execute
        assert calls == [1, 2, 3, 4]


class TestExecutorExceptionHandling:
    """Tests for exception handling during flush when executors raise."""

    def test_executor_exception_propagates_during_flush(self):
        """Test that executor exceptions propagate during flush (fail-fast)."""
        calls = []

        def task_a():
            calls.append('a')

        def failing_task():
            raise ValueError("Task failed!")

        def task_c():
            calls.append('c')

        # Custom executor that actually calls the task
        def sync_executor(intent):
            intent.task(*intent.args, **intent.kwargs)

        s = Scope(policy=AllowAll(), executor=sync_executor)
        s._add(make_intent(task_a))
        s._add(make_intent(failing_task))
        s._add(make_intent(task_c))

        # flush() should raise the exception from failing_task
        with pytest.raises(ValueError, match="Task failed!"):
            s.flush()

        # task_a should have executed, but task_c should not (fail-fast)
        assert calls == ['a']

        # Scope should still be marked as flushed
        assert s.is_flushed

    def test_executor_exception_during_context_manager_flush(self):
        """Test that executor exceptions propagate when flush happens in __exit__."""
        calls = []

        def task_a():
            calls.append('a')

        def failing_task():
            raise ValueError("Task failed!")

        def task_c():
            calls.append('c')

        def sync_executor(intent):
            intent.task(*intent.args, **intent.kwargs)

        # Using context manager - flush happens automatically
        with pytest.raises(ValueError, match="Task failed!"):
            with scope(policy=AllowAll(), executor=sync_executor):
                airlock.enqueue(task_a)
                airlock.enqueue(failing_task)
                airlock.enqueue(task_c)

        # task_a executed, task_c did not (fail-fast)
        assert calls == ['a']

    def test_executor_exception_with_empty_queue(self):
        """Test that executor with no intents doesn't raise."""
        def sync_executor(intent):
            raise ValueError("Should not be called")

        s = Scope(policy=AllowAll(), executor=sync_executor)
        # No intents added
        result = s.flush()

        assert result == []
        assert s.is_flushed