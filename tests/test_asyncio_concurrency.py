"""
Tests for asyncio concurrency safety.

These tests verify that airlock's context variable isolation works correctly
when multiple asyncio tasks run concurrently. This tests the native Python
asyncio integration, where contextvars are properly isolated per-task by default.

The tests require Python 3.7+ (for native contextvars support in asyncio).
"""

import asyncio
import pytest


def dummy_task(*args, **kwargs):
    """A dummy task for testing."""
    pass


class TestAsyncioContextIsolation:
    """
    Tests that verify context variable isolation across concurrent asyncio tasks.

    These tests simulate the worst-case interleaving scenario where tasks
    yield control to each other while scopes are active. If contextvars were
    shared across tasks, these tests would fail with cross-contamination
    between scopes.
    """

    @pytest.mark.asyncio
    async def test_concurrent_scopes_are_isolated(self):
        """
        Test that concurrent asyncio tasks each have isolated scopes.

        This is THE critical test. We spawn multiple tasks, each creating
        a scope and enqueueing intents. Tasks yield control to each other
        mid-scope. If isolation fails, intents would leak between scopes.
        """
        import airlock

        results = {}
        errors = []

        async def async_task(task_id: int):
            """A task that creates a scope, yields, and verifies isolation."""
            try:
                with airlock.scope() as s:
                    # Enqueue an intent with our ID
                    airlock.enqueue(dummy_task, task_id=task_id, phase="before")

                    # Yield control to other tasks - this is the scary part!
                    # If contextvars are shared, another task could overwrite
                    # our _current_scope here.
                    await asyncio.sleep(0)

                    # Enqueue another intent after yielding
                    airlock.enqueue(dummy_task, task_id=task_id, phase="after")

                    # Yield again for good measure
                    await asyncio.sleep(0)

                    # Verify our scope only has OUR intents
                    for intent in s.intents:
                        if intent.kwargs.get("task_id") != task_id:
                            errors.append(
                                f"Task {task_id} found intent from task "
                                f"{intent.kwargs.get('task_id')} in its scope!"
                            )

                    results[task_id] = {
                        "intent_count": len(s.intents),
                        "intent_ids": [i.kwargs.get("task_id") for i in s.intents],
                    }
            except Exception as e:
                errors.append(f"Task {task_id} raised: {e}")

        # Spawn many concurrent tasks
        num_tasks = 50
        tasks = [asyncio.create_task(async_task(i)) for i in range(num_tasks)]

        # Wait for all to complete
        await asyncio.gather(*tasks)

        # Check for errors
        assert not errors, f"Isolation failures detected:\n" + "\n".join(errors)

        # Verify each task saw exactly 2 intents (before and after yield)
        assert len(results) == num_tasks, f"Not all tasks completed: {len(results)}/{num_tasks}"

        for task_id, result in results.items():
            assert result["intent_count"] == 2, (
                f"Task {task_id} had {result['intent_count']} intents, expected 2"
            )
            assert result["intent_ids"] == [task_id, task_id], (
                f"Task {task_id} had wrong intent IDs: {result['intent_ids']}"
            )

    @pytest.mark.asyncio
    async def test_nested_scopes_across_tasks(self):
        """
        Test that nested scopes work correctly across concurrent asyncio tasks.

        Each task creates nested scopes, yields between operations, and
        verifies parent-child relationships are maintained.
        """
        import airlock

        results = {}
        errors = []

        async def async_task(task_id: int):
            try:
                with airlock.scope() as outer:
                    airlock.enqueue(dummy_task, task_id=task_id, scope="outer")
                    await asyncio.sleep(0)  # Yield

                    with airlock.scope() as inner:
                        airlock.enqueue(dummy_task, task_id=task_id, scope="inner")
                        await asyncio.sleep(0)  # Yield while nested

                        # Inner scope should have 1 intent
                        inner_intents = inner.intents
                        if len(inner_intents) != 1:
                            errors.append(
                                f"Task {task_id} inner scope has "
                                f"{len(inner_intents)} intents, expected 1"
                            )
                        for intent in inner_intents:
                            if intent.kwargs.get("task_id") != task_id:
                                errors.append(
                                    f"Task {task_id} inner scope has intent "
                                    f"from task {intent.kwargs.get('task_id')}"
                                )

                    await asyncio.sleep(0)  # Yield after inner scope exits

                    # Outer scope should have 2 intents (its own + captured from inner)
                    # because default behavior captures nested scope intents
                    outer_intents = outer.intents
                    for intent in outer_intents:
                        if intent.kwargs.get("task_id") != task_id:
                            errors.append(
                                f"Task {task_id} outer scope has intent "
                                f"from task {intent.kwargs.get('task_id')}"
                            )

                results[task_id] = True
            except Exception as e:
                errors.append(f"Task {task_id} raised: {e}")

        num_tasks = 30
        tasks = [asyncio.create_task(async_task(i)) for i in range(num_tasks)]
        await asyncio.gather(*tasks)

        assert not errors, f"Isolation failures:\n" + "\n".join(errors)
        assert len(results) == num_tasks

    @pytest.mark.asyncio
    async def test_rapid_scope_switching(self):
        """
        Stress test with rapid scope creation/destruction across asyncio tasks.

        This test creates a high-frequency switching pattern to catch any
        race conditions in context variable handling.
        """
        import airlock

        errors = []
        completed = []

        async def async_task(task_id: int):
            try:
                for iteration in range(10):
                    with airlock.scope() as s:
                        airlock.enqueue(dummy_task, task_id=task_id, iteration=iteration)
                        await asyncio.sleep(0)  # Yield mid-scope

                        # Verify isolation
                        for intent in s.intents:
                            if intent.kwargs.get("task_id") != task_id:
                                errors.append(
                                    f"Task {task_id} iteration {iteration}: "
                                    f"found intent from task {intent.kwargs.get('task_id')}"
                                )
                completed.append(task_id)
            except Exception as e:
                errors.append(f"Task {task_id} raised: {e}")

        num_tasks = 20
        tasks = [asyncio.create_task(async_task(i)) for i in range(num_tasks)]
        await asyncio.gather(*tasks)

        assert not errors, f"Isolation failures:\n" + "\n".join(errors)
        assert len(completed) == num_tasks


class TestSequentialAsyncioExecution:
    """
    Tests for sequential asyncio task execution (no concurrency).

    These verify that even without interleaving, context cleanup works
    correctly between sequential task executions.
    """

    @pytest.mark.asyncio
    async def test_sequential_tasks_dont_leak(self):
        """
        Test that sequentially executed asyncio tasks don't leak state.
        """
        import airlock

        results = []

        async def async_task(task_id: int):
            with airlock.scope() as s:
                airlock.enqueue(dummy_task, task_id=task_id)

                # Verify only our intent
                intents = s.intents
                assert len(intents) == 1
                assert intents[0].kwargs["task_id"] == task_id

                results.append(task_id)

        # Run tasks sequentially
        for i in range(10):
            await async_task(i)

        assert results == list(range(10))

    @pytest.mark.asyncio
    async def test_no_scope_leaks_between_tasks(self):
        """
        Verify that _current_scope is None between task executions.
        """
        import airlock
        from airlock import get_current_scope

        async def async_task():
            # Should start with no scope
            assert get_current_scope() is None

            with airlock.scope():
                assert get_current_scope() is not None

            # Should end with no scope
            assert get_current_scope() is None

        # Run multiple times
        for _ in range(5):
            await async_task()

        # Main context should also have no scope
        assert get_current_scope() is None


class TestAsyncioTaskCancellation:
    """
    Tests for asyncio task cancellation scenarios.

    These verify that scope cleanup happens correctly when tasks are cancelled.
    """

    @pytest.mark.asyncio
    async def test_cancelled_task_doesnt_leak_scope(self):
        """
        Test that a cancelled task doesn't leave a dangling scope.
        """
        import airlock
        from airlock import get_current_scope

        scope_was_active = False
        scope_after_cancel = None

        async def cancellable_task():
            nonlocal scope_was_active, scope_after_cancel
            try:
                with airlock.scope():
                    scope_was_active = True
                    # This will be cancelled
                    await asyncio.sleep(10)
            except asyncio.CancelledError:
                # Scope should be cleaned up by context manager
                scope_after_cancel = get_current_scope()
                raise

        task = asyncio.create_task(cancellable_task())

        # Give the task a moment to start and enter the scope
        await asyncio.sleep(0.01)

        # Cancel the task
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        assert scope_was_active, "Task should have entered the scope"
        assert scope_after_cancel is None, "Scope should be cleaned up after cancellation"
        assert get_current_scope() is None, "No scope should be active in main context"

    @pytest.mark.asyncio
    async def test_concurrent_cancellation_doesnt_affect_other_tasks(self):
        """
        Test that cancelling one task doesn't affect sibling tasks' scopes.
        """
        import airlock
        from airlock import get_current_scope

        results = {}
        errors = []

        async def normal_task(task_id: int):
            try:
                with airlock.scope() as s:
                    airlock.enqueue(dummy_task, task_id=task_id)
                    await asyncio.sleep(0.05)  # Long enough to overlap with cancellation

                    # Verify isolation
                    for intent in s.intents:
                        if intent.kwargs.get("task_id") != task_id:
                            errors.append(
                                f"Task {task_id} found intent from task "
                                f"{intent.kwargs.get('task_id')}"
                            )

                    results[task_id] = len(s.intents)
            except Exception as e:
                errors.append(f"Task {task_id} raised: {e}")

        async def task_to_cancel():
            try:
                with airlock.scope():
                    airlock.enqueue(dummy_task, task_id="cancelled")
                    await asyncio.sleep(10)  # Will be cancelled
            except asyncio.CancelledError:
                pass

        # Start normal tasks and the task we'll cancel
        normal_tasks = [asyncio.create_task(normal_task(i)) for i in range(5)]
        cancel_task = asyncio.create_task(task_to_cancel())

        # Give tasks time to start
        await asyncio.sleep(0.01)

        # Cancel one task
        cancel_task.cancel()

        # Wait for all tasks
        await asyncio.gather(*normal_tasks, cancel_task, return_exceptions=True)

        # All normal tasks should have completed successfully
        assert not errors, f"Errors detected:\n" + "\n".join(errors)
        assert len(results) == 5, f"Not all normal tasks completed: {results}"
        for task_id, intent_count in results.items():
            assert intent_count == 1, f"Task {task_id} had {intent_count} intents"
