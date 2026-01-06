import pytest
from unittest.mock import MagicMock, patch

import airlock
from airlock import Intent, AllowAll, ScopeStateError


# Configure Django settings before importing Django-dependent code
from django.conf import settings
if not settings.configured:
    settings.configure(
        DATABASES={"default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",  # In-memory database for tests
        }},
        INSTALLED_APPS=["django.contrib.contenttypes"],
    )

from django.test import override_settings
from airlock.integrations.django import DjangoScope, AirlockMiddleware, get_setting


def dummy_task():
    pass


def dummy_task_with_args(x, y):
    return x + y


@pytest.fixture
def mock_transaction():
    with patch("airlock.integrations.django.transaction") as m:
        yield m


def test_django_scope_flush_calls_on_commit(mock_transaction):
    """Test that DjangoScope registers flush with on_commit."""
    s = DjangoScope(policy=AllowAll())
    s._add(Intent(task=dummy_task, args=(), kwargs={}))

    s.flush()

    # Scope should be marked as flushed immediately
    assert s._flushed is True
    # on_commit should have been called
    mock_transaction.on_commit.assert_called_once()


def test_django_scope_flush_double_flush_raises():
    """Test that flushing twice raises ScopeStateError."""
    s = DjangoScope(policy=AllowAll())
    with patch("airlock.integrations.django.transaction"):
        s.flush()
        with pytest.raises(ScopeStateError, match="already been flushed"):
            s.flush()


# =============================================================================
# Real middleware integration tests (no mocking of airlock.scope)
# =============================================================================


def test_middleware_real_flush_on_success(mock_transaction):
    """Test middleware with real scope - flushes on 200 OK."""
    get_response = MagicMock()
    get_response.return_value.status_code = 200

    middleware = AirlockMiddleware(get_response)
    request = MagicMock()

    # This should work without raising
    response = middleware(request)

    assert response.status_code == 200


def test_middleware_real_discard_on_error(mock_transaction):
    """Test middleware with real scope - discards on 500 Error."""
    get_response = MagicMock()
    get_response.return_value.status_code = 500

    middleware = AirlockMiddleware(get_response)
    request = MagicMock()

    # This should work without raising
    response = middleware(request)

    assert response.status_code == 500


def test_middleware_real_discard_on_exception(mock_transaction):
    """Test middleware with real scope - discards on exception."""
    get_response = MagicMock()
    get_response.side_effect = ValueError("boom")

    middleware = AirlockMiddleware(get_response)
    request = MagicMock()

    # This should discard and re-raise, not raise ScopeStateError
    with pytest.raises(ValueError, match="boom"):
        middleware(request)


# =============================================================================
# Mock-based tests (for verifying flush/discard is called)
# =============================================================================


def test_middleware_flushes_on_success():
    """Test that middleware flushes on 200 OK."""
    get_response = MagicMock()
    get_response.return_value.status_code = 200

    middleware = AirlockMiddleware(get_response)
    request = MagicMock()

    with patch("airlock.integrations.django.airlock.scope") as mock_scope_cm:
        mock_s = MagicMock()
        mock_scope_cm.return_value.__enter__.return_value = mock_s

        middleware(request)

        mock_s.flush.assert_called_once()
        mock_s.discard.assert_not_called()


def test_middleware_discards_on_error():
    """Test that middleware discards on 500 Error."""
    get_response = MagicMock()
    get_response.return_value.status_code = 500

    middleware = AirlockMiddleware(get_response)
    request = MagicMock()

    with patch("airlock.integrations.django.airlock.scope") as mock_scope_cm:
        mock_s = MagicMock()
        mock_scope_cm.return_value.__enter__.return_value = mock_s

        middleware(request)

        mock_s.flush.assert_not_called()
        mock_s.discard.assert_called_once()


def test_middleware_discards_on_exception():
    """Test that middleware discards on exception."""
    get_response = MagicMock()
    get_response.side_effect = ValueError("boom")

    middleware = AirlockMiddleware(get_response)
    request = MagicMock()

    with patch("airlock.integrations.django.airlock.scope") as mock_scope_cm:
        mock_s = MagicMock()
        mock_scope_cm.return_value.__enter__.return_value = mock_s

        with pytest.raises(ValueError):
            middleware(request)

        mock_s.flush.assert_not_called()
        mock_s.discard.assert_called_once()


# =============================================================================
# get_executor() tests
# =============================================================================


def test_get_executor_returns_sync_when_backend_is_none():
    """Test get_executor returns sync_executor when TASK_BACKEND is None."""
    from airlock.integrations.django import get_executor
    from airlock.integrations.executors.sync import sync_executor

    with patch("airlock.integrations.django.get_setting") as mock_get_setting:
        mock_get_setting.return_value = None

        executor = get_executor()

        assert executor is sync_executor


def test_get_executor_imports_celery_executor():
    """Test get_executor imports celery_executor from dotted path."""
    from airlock.integrations.django import get_executor

    with patch("airlock.integrations.django.get_setting") as mock_get_setting:
        mock_get_setting.return_value = "airlock.integrations.executors.celery.celery_executor"

        executor = get_executor()

        # Should import and return the actual celery_executor
        from airlock.integrations.executors.celery import celery_executor
        assert executor is celery_executor


def test_get_executor_imports_django_q_executor():
    """Test get_executor imports django_q_executor from dotted path."""
    from airlock.integrations.django import get_executor

    with patch("airlock.integrations.django.get_setting") as mock_get_setting:
        mock_get_setting.return_value = "airlock.integrations.executors.django_q.django_q_executor"

        # Need to patch the django_q import since it may not be installed
        with patch("airlock.integrations.executors.django_q.async_task"):
            executor = get_executor()

            # Should import and return the actual django_q_executor
            from airlock.integrations.executors.django_q import django_q_executor
            assert executor is django_q_executor


def test_get_executor_imports_huey_executor():
    """Test get_executor imports huey_executor from dotted path."""
    from airlock.integrations.django import get_executor

    with patch("airlock.integrations.django.get_setting") as mock_get_setting:
        mock_get_setting.return_value = "airlock.integrations.executors.huey.huey_executor"

        executor = get_executor()

        # Should import and return the actual huey_executor
        from airlock.integrations.executors.huey import huey_executor
        assert executor is huey_executor


def test_get_executor_imports_dramatiq_executor():
    """Test get_executor imports dramatiq_executor from dotted path."""
    from airlock.integrations.django import get_executor

    with patch("airlock.integrations.django.get_setting") as mock_get_setting:
        mock_get_setting.return_value = "airlock.integrations.executors.dramatiq.dramatiq_executor"

        executor = get_executor()

        # Should import and return the actual dramatiq_executor
        from airlock.integrations.executors.dramatiq import dramatiq_executor
        assert executor is dramatiq_executor


def test_get_executor_custom_executor():
    """Test get_executor can import custom executor from user code."""
    from airlock.integrations.django import get_executor
    from airlock import Intent

    # Create a mock module with a custom executor
    def my_custom_executor(intent: Intent) -> None:
        pass

    mock_module = MagicMock()
    mock_module.my_custom_executor = my_custom_executor

    with patch("airlock.integrations.django.get_setting") as mock_get_setting:
        mock_get_setting.return_value = "myapp.executors.my_custom_executor"

        with patch("airlock.integrations.django.import_module") as mock_import:
            mock_import.return_value = mock_module

            executor = get_executor()

            assert executor is my_custom_executor
            mock_import.assert_called_once_with("myapp.executors")


# =============================================================================
# TASK_BACKEND setting integration tests
# =============================================================================


def test_django_scope_uses_sync_executor_by_default(mock_transaction):
    """Test DjangoScope uses sync_executor when TASK_BACKEND is None."""
    from airlock.integrations.executors.sync import sync_executor

    with patch("airlock.integrations.django.get_setting") as mock_get_setting:
        mock_get_setting.side_effect = lambda key: {
            "TASK_BACKEND": None,
            "DATABASE_ALIAS": "default",
            "USE_ON_COMMIT": True,
        }.get(key)

        scope = DjangoScope(policy=AllowAll())

        assert scope._executor is sync_executor


def test_django_scope_uses_celery_executor_from_setting(mock_transaction):
    """Test DjangoScope uses celery_executor when configured in TASK_BACKEND."""
    from airlock.integrations.executors.celery import celery_executor

    with patch("airlock.integrations.django.get_setting") as mock_get_setting:
        mock_get_setting.side_effect = lambda key: {
            "TASK_BACKEND": "airlock.integrations.executors.celery.celery_executor",
            "DATABASE_ALIAS": "default",
            "USE_ON_COMMIT": True,
        }.get(key)

        scope = DjangoScope(policy=AllowAll())

        assert scope._executor is celery_executor


def test_django_scope_uses_django_q_executor_from_setting(mock_transaction):
    """Test DjangoScope uses django_q_executor when configured in TASK_BACKEND."""
    with patch("airlock.integrations.django.get_setting") as mock_get_setting:
        mock_get_setting.side_effect = lambda key: {
            "TASK_BACKEND": "airlock.integrations.executors.django_q.django_q_executor",
            "DATABASE_ALIAS": "default",
            "USE_ON_COMMIT": True,
        }.get(key)

        with patch("airlock.integrations.executors.django_q.async_task"):
            scope = DjangoScope(policy=AllowAll())

            from airlock.integrations.executors.django_q import django_q_executor
            assert scope._executor is django_q_executor


def test_django_scope_explicit_executor_overrides_setting(mock_transaction):
    """Test explicit executor parameter overrides TASK_BACKEND setting."""
    from airlock.integrations.executors.celery import celery_executor
    from airlock.integrations.executors.huey import huey_executor

    with patch("airlock.integrations.django.get_setting") as mock_get_setting:
        mock_get_setting.side_effect = lambda key: {
            "TASK_BACKEND": "airlock.integrations.executors.celery.celery_executor",
            "DATABASE_ALIAS": "default",
            "USE_ON_COMMIT": True,
        }.get(key)

        # Explicitly pass huey_executor, should override celery from setting
        scope = DjangoScope(policy=AllowAll(), executor=huey_executor)

        assert scope._executor is huey_executor


def test_django_scope_dispatches_with_configured_executor(mock_transaction):
    """Test DjangoScope dispatches intents using configured executor."""

    # Create a custom executor we can track
    executed_intents = []

    def tracking_executor(intent):
        executed_intents.append(intent)

    with patch("airlock.integrations.django.get_setting") as mock_get_setting:
        mock_get_setting.side_effect = lambda key: {
            "TASK_BACKEND": None,  # Will be overridden by explicit executor
            "DATABASE_ALIAS": "default",
            "USE_ON_COMMIT": False,  # Dispatch immediately
        }.get(key)

        scope = DjangoScope(policy=AllowAll(), executor=tracking_executor)
        scope._add(Intent(task=dummy_task, args=(), kwargs={}))
        scope._add(Intent(task=dummy_task_with_args, args=(1, 2), kwargs={}))

        scope.flush()

        # Should have dispatched both intents using our tracking executor
        assert len(executed_intents) == 2
        assert executed_intents[0].task is dummy_task
        assert executed_intents[1].task is dummy_task_with_args


# =============================================================================
# Executor composition with scope tests
# =============================================================================


def test_base_scope_with_celery_executor():
    """Test base Scope works with celery_executor."""
    import airlock
    from airlock.integrations.executors.celery import celery_executor

    mock_task = MagicMock()
    mock_task.apply_async = MagicMock()

    with airlock.scope(executor=celery_executor):
        airlock.enqueue(mock_task, 1, 2, x=3)

    # Should have dispatched via celery
    mock_task.apply_async.assert_called_once_with(
        args=(1, 2),
        kwargs={"x": 3}
    )


def test_base_scope_with_django_q_executor():
    """Test base Scope works with django_q_executor."""
    import airlock
    from airlock.integrations.executors.django_q import django_q_executor

    with patch("airlock.integrations.executors.django_q.async_task") as mock_async_task:
        mock_task = MagicMock(__name__="my_task")

        with airlock.scope(executor=django_q_executor):
            airlock.enqueue(mock_task, 1, 2, x=3)

        # Should have dispatched via django-q
        mock_async_task.assert_called_once_with(mock_task, 1, 2, x=3)


def test_base_scope_with_huey_executor():
    """Test base Scope works with huey_executor."""
    import airlock
    from airlock.integrations.executors.huey import huey_executor

    mock_task = MagicMock()
    mock_task.schedule = MagicMock()

    with airlock.scope(executor=huey_executor):
        airlock.enqueue(mock_task, 1, 2, x=3)

    # Should have dispatched via huey
    mock_task.schedule.assert_called_once_with(
        args=(1, 2),
        kwargs={"x": 3}
    )


def test_base_scope_with_dramatiq_executor():
    """Test base Scope works with dramatiq_executor."""
    import airlock
    from airlock.integrations.executors.dramatiq import dramatiq_executor

    mock_task = MagicMock()
    mock_task.send_with_options = MagicMock()

    with airlock.scope(executor=dramatiq_executor):
        airlock.enqueue(mock_task, 1, 2, x=3)

    # Should have dispatched via dramatiq
    mock_task.send_with_options.assert_called_once_with(
        args=(1, 2),
        kwargs={"x": 3}
    )


def test_django_scope_with_multiple_executors_in_sequence():
    """Test different DjangoScopes can use different executors."""
    from airlock.integrations.executors.sync import sync_executor
    from airlock.integrations.executors.celery import celery_executor

    with patch("airlock.integrations.django.get_setting") as mock_get_setting:
        mock_get_setting.side_effect = lambda key: {
            "DATABASE_ALIAS": "default",
            "USE_ON_COMMIT": False,
        }.get(key)

        # First scope with sync executor
        executed_sync = []

        def tracking_sync(intent):
            executed_sync.append(intent)

        scope1 = DjangoScope(policy=AllowAll(), executor=tracking_sync)
        scope1._add(Intent(task=dummy_task, args=(), kwargs={}))
        scope1.flush()

        assert len(executed_sync) == 1

        # Second scope with celery executor
        mock_celery_task = MagicMock()
        mock_celery_task.apply_async = MagicMock()

        scope2 = DjangoScope(policy=AllowAll(), executor=celery_executor)
        scope2._add(Intent(task=mock_celery_task, args=(1,), kwargs={}))
        scope2.flush()

        mock_celery_task.apply_async.assert_called_once_with(
            args=(1,),
            kwargs={}
        )


# =============================================================================
# Executor exception handling tests
# =============================================================================


@override_settings(AIRLOCK={"USE_ON_COMMIT": False})
def test_use_on_commit_false():
    """Test USE_ON_COMMIT=False: exception propagates immediately from flush."""
    # Checkpoint trackers
    calls = []
    code_after_enqueue = []
    code_after_flush = []

    def task_a():
        calls.append('a')

    def failing_task():
        raise ValueError("Executor failed!")

    def task_c():
        calls.append('c')

    def sync_executor(intent):
        intent.task(*intent.args, **intent.kwargs)

    with pytest.raises(ValueError, match="Executor failed!"):
        with airlock.scope(policy=AllowAll(), _cls=DjangoScope, executor=sync_executor):
            airlock.enqueue(task_a)
            airlock.enqueue(failing_task)
            airlock.enqueue(task_c)
            code_after_enqueue.append(1)
        # scope.__exit__ flushes, exception propagates immediately
        code_after_flush.append(1)

    # Verify checkpoints
    assert calls == ['a']  # fail-fast: only task_a ran
    assert code_after_enqueue == [1]  # always runs
    assert code_after_flush == []  # doesn't run (exception propagated)


@override_settings(AIRLOCK={"USE_ON_COMMIT": True, "ROBUST": False})
def test_robust_false():
    """Test ROBUST=False: exception propagates from commit, stops other hooks."""
    from django.db import transaction

    # Checkpoint trackers
    calls = []
    code_after_enqueue = []
    code_after_flush = []
    other_hook_ran = []
    code_after_atomic = []

    def task_a():
        calls.append('a')

    def failing_task():
        raise ValueError("Executor failed!")

    def task_c():
        calls.append('c')

    def sync_executor(intent):
        intent.task(*intent.args, **intent.kwargs)

    with pytest.raises(ValueError, match="Executor failed!"):
        with transaction.atomic():
            with airlock.scope(policy=AllowAll(), _cls=DjangoScope, executor=sync_executor):
                airlock.enqueue(task_a)
                airlock.enqueue(failing_task)
                airlock.enqueue(task_c)
                code_after_enqueue.append(1)
            # scope.__exit__ flushes, registers on_commit callback
            code_after_flush.append(1)

            # Register another on_commit hook
            transaction.on_commit(lambda: other_hook_ran.append(1))
        # atomic.__exit__ commits, callbacks run, exception propagates
        code_after_atomic.append(1)

    # Verify checkpoints
    assert calls == ['a']  # fail-fast: only task_a ran
    assert code_after_enqueue == [1]  # always runs
    assert code_after_flush == [1]  # runs (flush succeeded)
    assert other_hook_ran == []  # doesn't run (robust=False stops other hooks)
    assert code_after_atomic == []  # doesn't run (exception propagated)


@override_settings(AIRLOCK={"USE_ON_COMMIT": True, "ROBUST": True})
def test_robust_true():
    """Test ROBUST=True (default): exception logged, other hooks continue."""
    from django.db import transaction

    # Checkpoint trackers
    calls = []
    code_after_enqueue = []
    code_after_flush = []
    other_hook_ran = []
    code_after_atomic = []

    def task_a():
        calls.append('a')

    def failing_task():
        raise ValueError("Executor failed!")

    def task_c():
        calls.append('c')

    def sync_executor(intent):
        intent.task(*intent.args, **intent.kwargs)

    # No exception propagates with robust=True
    with transaction.atomic():
        with airlock.scope(policy=AllowAll(), _cls=DjangoScope, executor=sync_executor):
            airlock.enqueue(task_a)
            airlock.enqueue(failing_task)
            airlock.enqueue(task_c)
            code_after_enqueue.append(1)
        # scope.__exit__ flushes, registers on_commit callback
        code_after_flush.append(1)

        # Register another on_commit hook
        transaction.on_commit(lambda: other_hook_ran.append(1))
    # atomic.__exit__ commits, callbacks run, exception logged (not propagated)
    code_after_atomic.append(1)

    # Verify checkpoints
    assert calls == ['a']  # fail-fast: only task_a ran
    assert code_after_enqueue == [1]  # always runs
    assert code_after_flush == [1]  # runs (flush succeeded)
    assert other_hook_ran == [1]  # runs (robust=True allows other hooks)
    assert code_after_atomic == [1]  # runs (no exception propagated)
