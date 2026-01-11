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

from django.db import transaction
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
# get_executor() tests
# =============================================================================


def test_get_executor_returns_sync_when_backend_is_none():
    """Test get_executor returns sync_executor when EXECUTOR is None."""
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
    import sys
    from airlock.integrations.django import get_executor

    # Mock django_q.tasks module before importing the executor
    mock_django_q_tasks = MagicMock()
    with patch.dict(sys.modules, {"django_q": MagicMock(), "django_q.tasks": mock_django_q_tasks}):
        # Clear any cached import of the executor module
        sys.modules.pop("airlock.integrations.executors.django_q", None)

        with patch("airlock.integrations.django.get_setting") as mock_get_setting:
            mock_get_setting.return_value = "airlock.integrations.executors.django_q.django_q_executor"

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

        # Patch importlib.import_module since get_executor imports it locally
        with patch("importlib.import_module") as mock_import:
            mock_import.return_value = mock_module

            executor = get_executor()

            assert executor is my_custom_executor
            mock_import.assert_called_once_with("myapp.executors")


# =============================================================================
# get_scope_class() tests
# =============================================================================


def test_get_scope_class_returns_django_scope_by_default():
    """Test get_scope_class returns DjangoScope when using default SCOPE setting."""
    from airlock.integrations.django import get_scope_class

    with patch("airlock.integrations.django.get_setting") as mock_get_setting:
        mock_get_setting.return_value = "airlock.integrations.django.DjangoScope"

        scope_class = get_scope_class()

        assert scope_class is DjangoScope


def test_get_scope_class_imports_custom_scope():
    """Test get_scope_class imports custom scope from dotted path."""
    from airlock.integrations.django import get_scope_class

    # Create a mock custom scope class
    class CustomScope(DjangoScope):
        pass

    mock_module = MagicMock()
    mock_module.CustomScope = CustomScope

    with patch("airlock.integrations.django.get_setting") as mock_get_setting:
        mock_get_setting.return_value = "myapp.scopes.CustomScope"

        with patch("airlock.integrations.django.import_string") as mock_import:
            mock_import.return_value = CustomScope

            scope_class = get_scope_class()

            assert scope_class is CustomScope
            mock_import.assert_called_once_with("myapp.scopes.CustomScope")


# =============================================================================
# get_policy() tests
# =============================================================================


def test_get_policy_with_callable():
    """Test get_policy() when POLICY setting is a callable."""
    from airlock.integrations.django import get_policy

    def policy_factory():
        return AllowAll()

    with patch("airlock.integrations.django.get_setting") as mock_get_setting:
        mock_get_setting.return_value = policy_factory

        policy = get_policy()

        assert isinstance(policy, AllowAll)


def test_get_policy_with_instance():
    """Test get_policy() when POLICY setting is already an instance."""
    from airlock.integrations.django import get_policy

    instance = AllowAll()

    with patch("airlock.integrations.django.get_setting") as mock_get_setting:
        mock_get_setting.return_value = instance

        policy = get_policy()

        assert policy is instance


def test_middleware_uses_scope_class_from_setting(mock_transaction):
    """Test AirlockMiddleware uses scope class from SCOPE setting."""
    # Create a custom scope class that tracks instantiation
    instantiated = []

    class TrackingScope(DjangoScope):
        def __init__(self, **kwargs):
            instantiated.append(self)
            super().__init__(**kwargs)

    get_response = MagicMock()
    get_response.return_value.status_code = 200

    with patch("airlock.integrations.django.get_scope_class") as mock_get_scope:
        mock_get_scope.return_value = TrackingScope
        with patch("airlock.integrations.django.get_policy") as mock_get_policy:
            mock_get_policy.return_value = AllowAll()

            middleware = AirlockMiddleware(get_response)
            request = MagicMock()

            middleware(request)

            # Should have instantiated our custom scope
            assert len(instantiated) == 1
            assert isinstance(instantiated[0], TrackingScope)


# =============================================================================
# EXECUTOR setting integration tests
# =============================================================================


def test_django_scope_uses_sync_executor_by_default(mock_transaction):
    """Test DjangoScope uses sync_executor when EXECUTOR is None."""
    from airlock.integrations.executors.sync import sync_executor

    with patch("airlock.integrations.django.get_setting") as mock_get_setting:
        mock_get_setting.side_effect = lambda key: {
            "EXECUTOR": None,
        }.get(key)

        scope = DjangoScope(policy=AllowAll())

        assert scope._executor is sync_executor


def test_django_scope_uses_celery_executor_from_setting(mock_transaction):
    """Test DjangoScope uses celery_executor when configured in EXECUTOR."""
    from airlock.integrations.executors.celery import celery_executor

    with patch("airlock.integrations.django.get_setting") as mock_get_setting:
        mock_get_setting.side_effect = lambda key: {
            "EXECUTOR": "airlock.integrations.executors.celery.celery_executor",
        }.get(key)

        scope = DjangoScope(policy=AllowAll())

        assert scope._executor is celery_executor


def test_django_scope_uses_django_q_executor_from_setting(mock_transaction):
    """Test DjangoScope uses django_q_executor when configured in EXECUTOR."""
    import sys

    # Mock django_q.tasks module before importing the executor
    mock_django_q_tasks = MagicMock()
    with patch.dict(sys.modules, {"django_q": MagicMock(), "django_q.tasks": mock_django_q_tasks}):
        # Clear any cached import of the executor module
        sys.modules.pop("airlock.integrations.executors.django_q", None)

        with patch("airlock.integrations.django.get_setting") as mock_get_setting:
            mock_get_setting.side_effect = lambda key: {
                "EXECUTOR": "airlock.integrations.executors.django_q.django_q_executor",
            }.get(key)

            scope = DjangoScope(policy=AllowAll())

            from airlock.integrations.executors.django_q import django_q_executor
            assert scope._executor is django_q_executor


def test_django_scope_explicit_executor_overrides_setting(mock_transaction):
    """Test explicit executor parameter overrides EXECUTOR setting."""
    from airlock.integrations.executors.celery import celery_executor
    from airlock.integrations.executors.huey import huey_executor

    with patch("airlock.integrations.django.get_setting") as mock_get_setting:
        mock_get_setting.side_effect = lambda key: {
            "EXECUTOR": "airlock.integrations.executors.celery.celery_executor",
        }.get(key)

        # Explicitly pass huey_executor, should override celery from setting
        scope = DjangoScope(policy=AllowAll(), executor=huey_executor)

        assert scope._executor is huey_executor


def test_django_scope_dispatches_with_configured_executor():
    """Test DjangoScope dispatches intents using configured executor."""

    # Create a custom executor we can track
    executed_intents = []

    def tracking_executor(intent):
        executed_intents.append(intent)

    with patch("airlock.integrations.django.get_setting") as mock_get_setting:
        mock_get_setting.side_effect = lambda key: {
            "EXECUTOR": None,  # Will be overridden by explicit executor
        }.get(key)

        # Wrap in transaction.atomic() so on_commit callback fires
        with transaction.atomic():
            scope = DjangoScope(policy=AllowAll(), executor=tracking_executor)
            scope._add(Intent(task=dummy_task, args=(), kwargs={}))
            scope._add(Intent(task=dummy_task_with_args, args=(1, 2), kwargs={}))
            scope.flush()
        # on_commit callbacks fire here when atomic block exits

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
    import sys
    import airlock

    # Mock django_q.tasks module before importing the executor
    mock_async_task = MagicMock()
    mock_django_q_tasks = MagicMock()
    mock_django_q_tasks.async_task = mock_async_task
    with patch.dict(sys.modules, {"django_q": MagicMock(), "django_q.tasks": mock_django_q_tasks}):
        # Clear any cached import of the executor module
        sys.modules.pop("airlock.integrations.executors.django_q", None)

        from airlock.integrations.executors.django_q import django_q_executor

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

    # First scope with tracking executor
    executed_sync = []

    def tracking_sync(intent):
        executed_sync.append(intent)

    with transaction.atomic():
        scope1 = DjangoScope(policy=AllowAll(), executor=tracking_sync)
        scope1._add(Intent(task=dummy_task, args=(), kwargs={}))
        scope1.flush()
    # on_commit fires here

    assert len(executed_sync) == 1

    # Second scope with celery executor
    mock_celery_task = MagicMock()
    mock_celery_task.apply_async = MagicMock()

    with transaction.atomic():
        scope2 = DjangoScope(policy=AllowAll(), executor=celery_executor)
        scope2._add(Intent(task=mock_celery_task, args=(1,), kwargs={}))
        scope2.flush()
    # on_commit fires here

    mock_celery_task.apply_async.assert_called_once_with(
        args=(1,),
        kwargs={}
    )


# =============================================================================
# Executor exception handling tests
# =============================================================================


class TestExecutorExceptionHandling:
    """Test exception handling in DjangoScope dispatch."""

    def setup_method(self):
        """Initialize checkpoint trackers and define tasks/executor."""
        # Checkpoint trackers
        self.calls = []
        self.code_after_enqueue = []
        self.code_after_flush = []
        self.other_hook_ran = []
        self.code_after_atomic = []

        # Task definitions
        def task_a():
            self.calls.append('a')

        def failing_task():
            raise ValueError("Executor failed!")

        def task_c():
            self.calls.append('c')

        self.task_a = task_a
        self.failing_task = failing_task
        self.task_c = task_c

        # Executor
        def sync_executor(intent):
            intent.task(*intent.args, **intent.kwargs)

        self.sync_executor = sync_executor

    def test_executor_exception_does_not_propagate(self):
        """Test that executor exceptions are logged but don't propagate (robust=True behavior)."""
        # DjangoScope schedules each intent orthogonally with robust=True,
        # so one failing doesn't prevent others from running
        with transaction.atomic():
            with airlock.scope(policy=AllowAll(), _cls=DjangoScope, executor=self.sync_executor):
                airlock.enqueue(self.task_a)
                airlock.enqueue(self.failing_task)
                airlock.enqueue(self.task_c)
                self.code_after_enqueue.append(1)
            # scope.__exit__ flushes, registers on_commit callbacks
            self.code_after_flush.append(1)

            # Register another on_commit hook
            transaction.on_commit(lambda: self.other_hook_ran.append(1))
        # atomic.__exit__ commits, callbacks run, exception logged (not propagated)
        self.code_after_atomic.append(1)

        # Verify checkpoints
        assert self.calls == ['a', 'c']  # both run; failing_task logged but didn't block
        assert self.code_after_enqueue == [1]  # always runs
        assert self.code_after_flush == [1]  # runs (flush succeeded)
        assert self.other_hook_ran == [1]  # runs (robust=True allows other hooks)
        assert self.code_after_atomic == [1]  # runs (no exception propagated)


# =============================================================================
# airlock_command decorator tests
# =============================================================================


def test_airlock_command_uses_get_policy(mock_transaction):
    """Test airlock_command uses get_policy() for policy."""
    from airlock.integrations.django import airlock_command

    executed = []

    class FakeCommand:
        @airlock_command
        def handle(self, *args, **options):
            executed.append(1)
            airlock.enqueue(dummy_task)

    with patch("airlock.integrations.django.get_policy") as mock_get_policy:
        mock_get_policy.return_value = AllowAll()
        with patch("airlock.integrations.django.get_scope_class") as mock_get_scope:
            mock_get_scope.return_value = DjangoScope

            cmd = FakeCommand()
            cmd.handle()

            mock_get_policy.assert_called_once()
            mock_get_scope.assert_called_once()

    assert executed == [1]


def test_airlock_command_uses_get_scope_class(mock_transaction):
    """Test airlock_command uses get_scope_class() for scope."""
    from airlock.integrations.django import airlock_command

    instantiated = []

    class TrackingScope(DjangoScope):
        def __init__(self, **kwargs):
            instantiated.append(self)
            super().__init__(**kwargs)

    class FakeCommand:
        @airlock_command
        def handle(self, *args, **options):
            airlock.enqueue(dummy_task)

    with patch("airlock.integrations.django.get_policy") as mock_get_policy:
        mock_get_policy.return_value = AllowAll()
        with patch("airlock.integrations.django.get_scope_class") as mock_get_scope:
            mock_get_scope.return_value = TrackingScope

            cmd = FakeCommand()
            cmd.handle()

    assert len(instantiated) == 1
    assert isinstance(instantiated[0], TrackingScope)


def test_airlock_command_dry_run_uses_drop_all(mock_transaction):
    """Test airlock_command uses DropAll policy when dry_run=True."""
    from airlock.integrations.django import airlock_command
    from airlock import DropAll

    policy_used = []

    class TrackingScope(DjangoScope):
        def __init__(self, policy, **kwargs):
            policy_used.append(policy)
            super().__init__(policy=policy, **kwargs)

    class FakeCommand:
        @airlock_command
        def handle(self, *args, **options):
            airlock.enqueue(dummy_task)

    with patch("airlock.integrations.django.get_policy") as mock_get_policy:
        mock_get_policy.return_value = AllowAll()
        with patch("airlock.integrations.django.get_scope_class") as mock_get_scope:
            mock_get_scope.return_value = TrackingScope

            cmd = FakeCommand()
            cmd.handle(dry_run=True)

            # get_policy should NOT be called when dry_run=True
            mock_get_policy.assert_not_called()

    assert len(policy_used) == 1
    assert isinstance(policy_used[0], DropAll)


def test_airlock_command_with_parens_and_custom_kwarg(mock_transaction):
    """Test @airlock_command() with parentheses and custom dry_run_kwarg."""
    from airlock.integrations.django import airlock_command
    from airlock import DropAll

    policy_used = []

    class TrackingScope(DjangoScope):
        def __init__(self, policy, **kwargs):
            policy_used.append(policy)
            super().__init__(policy=policy, **kwargs)

    class FakeCommand:
        @airlock_command(dry_run_kwarg="simulate")
        def handle(self, *args, **options):
            airlock.enqueue(dummy_task)

    with patch("airlock.integrations.django.get_policy") as mock_get_policy:
        mock_get_policy.return_value = AllowAll()
        with patch("airlock.integrations.django.get_scope_class") as mock_get_scope:
            mock_get_scope.return_value = TrackingScope

            cmd = FakeCommand()
            cmd.handle(simulate=True)

            # get_policy should NOT be called when simulate=True
            mock_get_policy.assert_not_called()

    assert len(policy_used) == 1
    assert isinstance(policy_used[0], DropAll)
