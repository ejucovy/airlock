"""
Tests for greenlet concurrency safety.

These tests verify that airlock's context variable isolation works correctly
when multiple greenlets run concurrently in the same thread. This is the
"scary" scenario where, without proper isolation, scopes could leak across
greenlets.

The tests require gevent and will be skipped if it's not installed.
"""

import pytest

try:
    import gevent
    from gevent import spawn, joinall, sleep as gsleep
    import greenlet

    GEVENT_AVAILABLE = True
    GREENLET_CONTEXTVAR_SAFE = getattr(greenlet, "GREENLET_USE_CONTEXT_VARS", False)
except ImportError:
    GEVENT_AVAILABLE = False
    GREENLET_CONTEXTVAR_SAFE = False


pytestmark = pytest.mark.skipif(
    not GEVENT_AVAILABLE,
    reason="gevent not installed",
)


def dummy_task(*args, **kwargs):
    """A dummy task for testing."""
    pass


class TestGreenletContextIsolation:
    """
    Tests that verify context variable isolation across concurrent greenlets.

    These tests simulate the worst-case interleaving scenario where greenlets
    yield control to each other while scopes are active. If contextvars were
    shared (as in old greenlet <1.0), these tests would fail with cross-
    contamination between scopes.
    """

    def test_greenlet_has_contextvar_support(self):
        """Verify that the installed greenlet version supports contextvars."""
        assert GREENLET_CONTEXTVAR_SAFE, (
            f"greenlet.GREENLET_USE_CONTEXT_VARS is False. "
            f"airlock requires greenlet>=1.0 for safe concurrent operation. "
            f"Installed greenlet version may be too old."
        )

    def test_concurrent_scopes_are_isolated(self):
        """
        Test that concurrent greenlets each have isolated scopes.

        This is THE critical test. We spawn multiple greenlets, each creating
        a scope and enqueueing intents. Greenlets yield control to each other
        mid-scope. If isolation fails, intents would leak between scopes.
        """
        import airlock

        results = {}
        errors = []

        def greenlet_task(task_id: int):
            """A task that creates a scope, yields, and verifies isolation."""
            try:
                with airlock.scope() as s:
                    # Enqueue an intent with our ID
                    airlock.enqueue(dummy_task, task_id=task_id, phase="before")

                    # Yield control to other greenlets - this is the scary part!
                    # If contextvars are shared, another greenlet could overwrite
                    # our _current_scope here.
                    gsleep(0)

                    # Enqueue another intent after yielding
                    airlock.enqueue(dummy_task, task_id=task_id, phase="after")

                    # Yield again for good measure
                    gsleep(0)

                    # Verify our scope only has OUR intents
                    for intent in s.intents:
                        if intent.kwargs.get("task_id") != task_id:
                            errors.append(
                                f"Greenlet {task_id} found intent from task "
                                f"{intent.kwargs.get('task_id')} in its scope!"
                            )

                    results[task_id] = {
                        "intent_count": len(s.intents),
                        "intent_ids": [i.kwargs.get("task_id") for i in s.intents],
                    }
            except Exception as e:
                errors.append(f"Greenlet {task_id} raised: {e}")

        # Spawn many concurrent greenlets
        num_greenlets = 50
        greenlets = [spawn(greenlet_task, i) for i in range(num_greenlets)]

        # Wait for all to complete
        joinall(greenlets)

        # Check for errors
        assert not errors, f"Isolation failures detected:\n" + "\n".join(errors)

        # Verify each greenlet saw exactly 2 intents (before and after yield)
        assert len(results) == num_greenlets, f"Not all greenlets completed: {len(results)}/{num_greenlets}"

        for task_id, result in results.items():
            assert result["intent_count"] == 2, (
                f"Greenlet {task_id} had {result['intent_count']} intents, expected 2"
            )
            assert result["intent_ids"] == [task_id, task_id], (
                f"Greenlet {task_id} had wrong intent IDs: {result['intent_ids']}"
            )

    def test_nested_scopes_across_greenlets(self):
        """
        Test that nested scopes work correctly across concurrent greenlets.

        Each greenlet creates nested scopes, yields between operations, and
        verifies parent-child relationships are maintained.
        """
        import airlock

        results = {}
        errors = []

        def greenlet_task(task_id: int):
            try:
                with airlock.scope() as outer:
                    airlock.enqueue(dummy_task, task_id=task_id, scope="outer")
                    gsleep(0)  # Yield

                    with airlock.scope() as inner:
                        airlock.enqueue(dummy_task, task_id=task_id, scope="inner")
                        gsleep(0)  # Yield while nested

                        # Inner scope should have 1 intent
                        inner_intents = inner.intents
                        if len(inner_intents) != 1:
                            errors.append(
                                f"Greenlet {task_id} inner scope has "
                                f"{len(inner_intents)} intents, expected 1"
                            )
                        for intent in inner_intents:
                            if intent.kwargs.get("task_id") != task_id:
                                errors.append(
                                    f"Greenlet {task_id} inner scope has intent "
                                    f"from task {intent.kwargs.get('task_id')}"
                                )

                    gsleep(0)  # Yield after inner scope exits

                    # Outer scope should have 2 intents (its own + captured from inner)
                    # because default behavior captures nested scope intents
                    outer_intents = outer.intents
                    for intent in outer_intents:
                        if intent.kwargs.get("task_id") != task_id:
                            errors.append(
                                f"Greenlet {task_id} outer scope has intent "
                                f"from task {intent.kwargs.get('task_id')}"
                            )

                results[task_id] = True
            except Exception as e:
                errors.append(f"Greenlet {task_id} raised: {e}")

        num_greenlets = 30
        greenlets = [spawn(greenlet_task, i) for i in range(num_greenlets)]
        joinall(greenlets)

        assert not errors, f"Isolation failures:\n" + "\n".join(errors)
        assert len(results) == num_greenlets

    def test_rapid_scope_switching(self):
        """
        Stress test with rapid scope creation/destruction across greenlets.

        This test creates a high-frequency switching pattern to catch any
        race conditions in context variable handling.
        """
        import airlock

        errors = []
        completed = []

        def greenlet_task(task_id: int):
            try:
                for iteration in range(10):
                    with airlock.scope() as s:
                        airlock.enqueue(dummy_task, task_id=task_id, iteration=iteration)
                        gsleep(0)  # Yield mid-scope

                        # Verify isolation
                        for intent in s.intents:
                            if intent.kwargs.get("task_id") != task_id:
                                errors.append(
                                    f"Greenlet {task_id} iteration {iteration}: "
                                    f"found intent from task {intent.kwargs.get('task_id')}"
                                )
                completed.append(task_id)
            except Exception as e:
                errors.append(f"Greenlet {task_id} raised: {e}")

        num_greenlets = 20
        greenlets = [spawn(greenlet_task, i) for i in range(num_greenlets)]
        joinall(greenlets)

        assert not errors, f"Isolation failures:\n" + "\n".join(errors)
        assert len(completed) == num_greenlets


class TestSequentialGreenletExecution:
    """
    Tests for sequential greenlet execution (no concurrency).

    These verify that even without interleaving, context cleanup works
    correctly between sequential greenlet executions.
    """

    def test_sequential_greenlets_dont_leak(self):
        """
        Test that sequentially executed greenlets don't leak state.
        """
        import airlock

        results = []

        def greenlet_task(task_id: int):
            with airlock.scope() as s:
                airlock.enqueue(dummy_task, task_id=task_id)

                # Verify only our intent
                intents = s.intents
                assert len(intents) == 1
                assert intents[0].kwargs["task_id"] == task_id

                results.append(task_id)

        # Run greenlets sequentially
        for i in range(10):
            g = spawn(greenlet_task, i)
            g.join()

        assert results == list(range(10))

    def test_no_scope_leaks_between_greenlets(self):
        """
        Verify that _current_scope is None between greenlet executions.
        """
        import airlock
        from airlock import get_current_scope

        def greenlet_task():
            # Should start with no scope
            assert get_current_scope() is None

            with airlock.scope():
                assert get_current_scope() is not None

            # Should end with no scope
            assert get_current_scope() is None

        # Run multiple times
        for _ in range(5):
            g = spawn(greenlet_task)
            g.join()

        # Main greenlet should also have no scope
        assert get_current_scope() is None
