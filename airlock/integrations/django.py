"""
Django integration for airlock.

Provides:
- DjangoScope: Defers dispatch to transaction.on_commit()
- AirlockMiddleware: Wraps requests in a scope
- airlock_command: Decorator for management commands
- get_executor(): Helper to select executor based on TASK_BACKEND setting

Settings (in settings.py):
    AIRLOCK = {
        "DEFAULT_POLICY": "airlock.AllowAll",  # Dotted path or callable
        "USE_ON_COMMIT": True,              # Defer dispatch to transaction.on_commit
        "DATABASE_ALIAS": "default",        # Database for on_commit
        "TASK_BACKEND": None,               # Dotted path to executor callable
    }

TASK_BACKEND is a dotted import path to an executor callable:
    - None (default): sync_executor (synchronous execution)
    - "airlock.integrations.executors.celery.celery_executor"
    - "airlock.integrations.executors.django_q.django_q_executor"
    - "airlock.integrations.executors.huey.huey_executor"
    - "airlock.integrations.executors.dramatiq.dramatiq_executor"
    - "myapp.executors.custom_executor" (or any custom executor)
"""

from functools import wraps
from typing import Any, Callable
from importlib import import_module

from django.conf import settings
from django.db import transaction, DEFAULT_DB_ALIAS

import airlock
from airlock import Scope, Intent, Executor, AllowAll, DropAll, _execute


# =============================================================================
# Settings
# =============================================================================

DEFAULTS = {
    "DEFAULT_POLICY": "airlock.AllowAll",
    "USE_ON_COMMIT": True,
    "DATABASE_ALIAS": DEFAULT_DB_ALIAS,
    "TASK_BACKEND": None,  # Dotted path to executor callable, or None for sync
}


def get_setting(name: str) -> Any:
    """Get an airlock setting, falling back to defaults."""
    user_settings = getattr(settings, "AIRLOCK", {})
    return user_settings.get(name, DEFAULTS[name])


def import_string(dotted_path: str) -> Any:
    """Import a class or function from a dotted path."""
    module_path, class_name = dotted_path.rsplit(".", 1)
    module = import_module(module_path)
    return getattr(module, class_name)


def get_default_policy():
    """Get the default policy instance."""
    policy_setting = get_setting("DEFAULT_POLICY")
    if callable(policy_setting):
        return policy_setting()
    if isinstance(policy_setting, str):
        policy_class = import_string(policy_setting)
        return policy_class()
    return policy_setting


# =============================================================================
# Executor selection
# =============================================================================


def get_executor() -> Executor:
    """
    Get the appropriate executor based on TASK_BACKEND setting.

    TASK_BACKEND should be a dotted import path to an executor callable,
    or None for synchronous execution.

    Examples:
        AIRLOCK = {
            'TASK_BACKEND': 'airlock.integrations.executors.django_q.django_q_executor',
        }

        # Or use a custom executor
        AIRLOCK = {
            'TASK_BACKEND': 'myapp.executors.custom_executor',
        }

    Returns:
        Executor function based on TASK_BACKEND

    Raises:
        ImportError: If the executor module/callable cannot be imported
    """
    from importlib import import_module

    backend = get_setting("TASK_BACKEND")

    if backend is None:
        from airlock.integrations.executors.sync import sync_executor
        return sync_executor

    # Import the callable from dotted path
    module_path, callable_name = backend.rsplit(".", 1)
    module = import_module(module_path)
    return getattr(module, callable_name)


# =============================================================================
# DjangoScope
# =============================================================================


class DjangoScope(Scope):
    """
    A Django-specific scope that respects database transactions.

    Defers dispatch to transaction.on_commit() so side effects only
    fire after the transaction commits successfully.

    If no executor is provided, uses get_executor() to select one based
    on TASK_BACKEND setting.
    """

    def __init__(
        self,
        *,
        using: str | None = None,
        executor: Executor | None = None,
        **kwargs: Any
    ) -> None:
        # Default to executor based on TASK_BACKEND setting if not provided
        if executor is None:
            executor = get_executor()

        super().__init__(executor=executor, **kwargs)
        self.using = using or get_setting("DATABASE_ALIAS")

    def _dispatch_all(self, intents: list[Intent]) -> None:
        """
        Dispatch intents, optionally deferring to on_commit.

        Uses self._executor (configured via constructor or TASK_BACKEND setting)
        to actually execute intents.

        Exception behavior:
            The exception behavior depends on the USE_ON_COMMIT setting:

            USE_ON_COMMIT=False (immediate dispatch):
                Executor exceptions propagate immediately during flush(), just like
                the base Scope class. This allows errors to be caught and handled
                synchronously.

            USE_ON_COMMIT=True (deferred dispatch, default):
                Dispatch is deferred until transaction.on_commit(). Executor exceptions
                propagate during transaction commit (robust=False is Django's default).

                This means:
                - flush() succeeds (it only registers the callback)
                - The exception propagates when the transaction commits
                - In middleware: this happens during request handling, BEFORE response sent
                - Errors are LOUD - they will cause request failures

                Note: robust=False means if this callback fails, other on_commit hooks
                are NOT executed. robust=True would continue other hooks but airlock uses
                the default to ensure loud failures.

            Fail-fast behavior:
                In both cases, if an executor raises an exception, the dispatch loop
                stops immediately and remaining intents are not dispatched (fail-fast).
        """
        if get_setting("USE_ON_COMMIT"):
            def do_dispatch():
                for intent in intents:
                    self._executor(intent)
            transaction.on_commit(do_dispatch, using=self.using, robust=False)
        else:
            for intent in intents:
                self._executor(intent)


# =============================================================================
# Middleware
# =============================================================================


class AirlockMiddleware:
    """
    Django middleware that wraps each request in an airlock scope.

    By default:
    - 1xx/2xx/3xx responses: flush
    - 4xx/5xx responses or exceptions: discard

    Subclass and override should_flush() for custom behavior.
    """

    def __init__(self, get_response: Callable) -> None:
        self.get_response = get_response

    def should_flush(self, request, response) -> bool:
        """Override to customize flush behavior."""
        return response.status_code < 400

    def __call__(self, request):
        policy = get_default_policy()

        # Use imperative API for manual terminal state handling.
        # This allows us to decide flush vs discard based on response status.
        s = DjangoScope(policy=policy)
        s.enter()
        request.airlock_scope = s

        exception = None
        response = None

        try:
            response = self.get_response(request)
        except Exception as e:
            exception = e
        finally:
            # Exit scope first - resets context var so flush/discard is allowed
            s.exit()

        # Terminal state handling (scope no longer active)
        if exception is not None:
            s.discard()
            raise exception

        if self.should_flush(request, response):
            s.flush()
        else:
            s.discard()

        return response


# =============================================================================
# Management command decorator
# =============================================================================


def airlock_command(
    func: Callable = None, *, dry_run_kwarg: str = "dry_run"
) -> Callable:
    """
    Decorator for Django management commands.

    Wraps the handle() method in an airlock scope.
    If options[dry_run_kwarg] is True, uses DropAll policy.

    Transaction semantics:
        Flush occurs at the end of handle(). If USE_ON_COMMIT is True (default),
        dispatch is deferred to transaction.on_commit(). This means:

        - With an active transaction: dispatch occurs after commit
        - Without a transaction: dispatch occurs immediately at end of handle()

        In practice, for most management commands that don't wrap their logic
        in transaction.atomic(), the mental boundary is still "end of handle()".

    Usage:
        class Command(BaseCommand):
            def add_arguments(self, parser):
                parser.add_argument('--dry-run', action='store_true')

            @airlock_command
            def handle(self, *args, **options):
                airlock.enqueue(some_task, ...)
    """

    def decorator(handle_func: Callable) -> Callable:
        @wraps(handle_func)
        def wrapper(self, *args, **options):
            is_dry_run = options.get(dry_run_kwarg, False)
            policy = DropAll() if is_dry_run else get_default_policy()

            with airlock.scope(policy=policy, _cls=DjangoScope):
                return handle_func(self, *args, **options)

        return wrapper

    if func is not None:
        return decorator(func)
    return decorator
