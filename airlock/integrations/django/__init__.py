"""Django integration for airlock.

Provides:

- `AirlockConfig`: AppConfig for auto-configuration via ``INSTALLED_APPS``
- `DjangoScope`: Defers dispatch to ``transaction.on_commit()``
- `AirlockMiddleware`: Wraps requests in a scope
- `get_executor()`: Helper to select executor based on ``EXECUTOR`` setting

For management commands and Celery tasks, use ``@airlock.scoped()`` decorator.

Quick Start::

    # settings.py
    INSTALLED_APPS = [
        ...
        "airlock.integrations.django",  # Auto-configures airlock
    ]

This automatically configures ``airlock.scope()`` and ``@airlock.scoped()`` to use:

- `DjangoScope` (defers dispatch to ``transaction.on_commit``)
- Policy and executor from ``AIRLOCK`` settings

Settings (in ``settings.py``)::

    AIRLOCK = {
        "POLICY": "airlock.AllowAll",  # Dotted path or callable
        "EXECUTOR": None,              # Dotted path to executor callable
        "SCOPE": "airlock.integrations.django.DjangoScope",  # Scope class for middleware
    }

``EXECUTOR`` is a dotted import path to an executor callable:

- ``None`` (default): ``sync_executor`` (synchronous execution)
- ``"airlock.integrations.executors.celery.celery_executor"``
- ``"airlock.integrations.executors.django_q.django_q_executor"``
- ``"airlock.integrations.executors.huey.huey_executor"``
- ``"airlock.integrations.executors.dramatiq.dramatiq_executor"``
- ``"myapp.executors.custom_executor"`` (or any custom executor)
"""

from functools import wraps
from typing import Any, Callable
from importlib import import_module

from django.conf import settings
from django.db import transaction

import airlock
from airlock import Scope, Intent, Executor, AllowAll, DropAll, _execute
from airlock.integrations.executors.sync import sync_executor


# =============================================================================
# Settings
# =============================================================================

DEFAULTS = {
    "POLICY": "airlock.AllowAll",
    "EXECUTOR": None,  # Dotted path to executor callable, or None for sync
    "SCOPE": "airlock.integrations.django.DjangoScope",
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


def get_policy():
    """Get the policy instance based on ``POLICY`` setting."""
    policy_setting = get_setting("POLICY")
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
    """Get the appropriate executor based on ``EXECUTOR`` setting.

    ``EXECUTOR`` should be a dotted import path to an executor callable,
    or ``None`` for synchronous execution.

    Example::

        AIRLOCK = {
            'EXECUTOR': 'airlock.integrations.executors.django_q.django_q_executor',
        }

        # Or use a custom executor
        AIRLOCK = {
            'EXECUTOR': 'myapp.executors.custom_executor',
        }

    Returns:
        Executor function based on ``EXECUTOR`` setting.

    Raises:
        ImportError: If the executor module/callable cannot be imported.
    """
    executor_path = get_setting("EXECUTOR")

    if executor_path is None:
        return sync_executor

    # Import the callable from dotted path
    module_path, callable_name = executor_path.rsplit(".", 1)
    module = import_module(module_path)
    return getattr(module, callable_name)


def get_scope_class():
    """Get the scope class to use, based on ``SCOPE`` setting."""
    scope_class_path = get_setting("SCOPE")
    return import_string(scope_class_path)


# =============================================================================
# DjangoScope
# =============================================================================


class DjangoScope(Scope):
    """A Django-specific scope that respects database transactions.

    Defers dispatch to ``transaction.on_commit()`` so side effects only
    fire after the transaction commits successfully. When called outside
    a transaction (autocommit mode), ``on_commit`` executes immediately.

    If no executor is provided, uses `get_executor()` to select one based
    on ``EXECUTOR`` setting.

    Subclass and override `schedule_dispatch()` to customize dispatch timing.
    """

    def __init__(
        self,
        *,
        executor: Executor | None = None,
        **kwargs: Any
    ) -> None:
        # Default to executor based on EXECUTOR setting if not provided
        if executor is None:
            executor = get_executor()

        super().__init__(executor=executor, **kwargs)

    def schedule_dispatch(self, callback: Callable[[], None]) -> None:
        """Schedule the dispatch callback. Override to customize dispatch timing.

        By default, uses ``transaction.on_commit(robust=True)``. This defers
        dispatch until the transaction commits, or runs immediately if
        outside a transaction (autocommit mode).

        Override to change timing, robust behavior, or skip ``on_commit`` entirely.
        """
        transaction.on_commit(callback, robust=True)

    def _dispatch_all(self, intents: list[Intent]) -> None:
        """Dispatch each intent via `schedule_dispatch()`, orthogonally."""
        for intent in intents:
            # Wrap in lambda to give Django's on_commit logging a __qualname__
            self.schedule_dispatch(lambda i=intent: self._executor(i))


# =============================================================================
# Middleware
# =============================================================================


class AirlockMiddleware:
    """Django middleware that wraps each request in an airlock scope.

    By default:

    - 1xx/2xx/3xx responses: flush
    - 4xx/5xx responses or exceptions: discard

    Subclass and override `should_flush()` for custom behavior.
    """

    def __init__(self, get_response: Callable) -> None:
        self.get_response = get_response

    def should_flush(self, request, response) -> bool:
        """Override to customize flush behavior.

        Returns:
            ``True`` to flush (dispatch intents), ``False`` to discard.
        """
        return response.status_code < 400

    def __call__(self, request):
        policy = get_policy()
        scope_class = get_scope_class()

        # Use imperative API for manual terminal state handling.
        # This allows us to decide flush vs discard based on response status.
        s = scope_class(policy=policy)
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


# Default app config for Django < 3.2 compatibility
default_app_config = "airlock.integrations.django.apps.AirlockConfig"
