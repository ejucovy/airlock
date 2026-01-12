"""Celery integration for airlock.

Provides:

- `LegacyTaskShim`: Migration helper for converting ``.delay()`` calls
- `install_global_intercept`: Patch all tasks to route through airlock

For wrapping task execution, use ``@airlock.scoped()`` decorator::

    @app.task
    @airlock.scoped()
    def my_task():
        airlock.enqueue(downstream_task, ...)
"""

import warnings
from typing import Any, TYPE_CHECKING

from celery import Task

import airlock
from airlock import AllowAll, get_current_scope

if TYPE_CHECKING:
    from celery import Celery


class LegacyTaskShim(Task):
    """Migration helper that intercepts ``.delay()`` and routes through airlock.

    Emits `DeprecationWarning` to encourage updating call sites.

    Example::

        @app.task(base=LegacyTaskShim)
        def old_task(...):
            ...

        # This now goes through airlock:
        old_task.delay(...)  # DeprecationWarning
    """

    def delay(self, *args: Any, **kwargs: Any) -> None:
        warnings.warn(
            f"Direct call to {self.name}.delay() is deprecated. "
            f"Use airlock.enqueue({self.name}, ...) instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        # Route through airlock - use self (the task) as the callable
        airlock.enqueue(self, *args, **kwargs)

    def apply_async(
        self,
        args: tuple[Any, ...] | None = None,
        kwargs: dict[str, Any] | None = None,
        **options: Any,
    ) -> Any:
        warnings.warn(
            f"Direct call to {self.name}.apply_async() is deprecated. "
            f"Use airlock.enqueue({self.name}, ..., _dispatch_options=...) instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        airlock.enqueue(
            self,
            *(args or ()),
            _dispatch_options=options if options else None,
            **(kwargs or {}),
        )


# =============================================================================
# Global intercept
# =============================================================================

_original_delay = None
_original_apply_async = None
_original_call = None
_installed = False
_wrap_execution = False


def _intercepted_delay(self, *args: Any, **kwargs: Any) -> Any:
    """Replacement for ``Task.delay()`` that routes through airlock when in scope.

    Always emits a deprecation warning to encourage migration to ``airlock.enqueue()``.
    """
    scope = get_current_scope()

    if scope is not None:
        # Inside an airlock scope - route through airlock
        warnings.warn(
            f"Direct call to {self.name}.delay() is deprecated. "
            f"Use airlock.enqueue({self.name}, ...) instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        airlock.enqueue(self, *args, **kwargs)
        return None  # Can't return AsyncResult when going through airlock
    else:
        # No scope - warn but pass through to original
        warnings.warn(
            f"Direct call to {self.name}.delay() is deprecated. "
            f"Use airlock.enqueue({self.name}, ...) instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return _original_delay(self, *args, **kwargs)


def _intercepted_apply_async(
    self,
    args: tuple[Any, ...] | None = None,
    kwargs: dict[str, Any] | None = None,
    **options: Any,
) -> Any:
    """Replacement for ``Task.apply_async()`` that routes through airlock when in scope.

    Always emits a deprecation warning to encourage migration to ``airlock.enqueue()``.
    """
    scope = get_current_scope()

    if scope is not None:
        # Inside an airlock scope - route through airlock with options preserved
        warnings.warn(
            f"Direct call to {self.name}.apply_async() is deprecated. "
            f"Use airlock.enqueue({self.name}, ..., _dispatch_options=...) instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        airlock.enqueue(
            self,
            *(args or ()),
            _dispatch_options=options if options else None,
            **(kwargs or {}),
        )
        return None  # Can't return AsyncResult when going through airlock
    else:
        # No scope - warn but pass through to original
        warnings.warn(
            f"Direct call to {self.name}.apply_async() is deprecated. "
            f"Use airlock.enqueue({self.name}, ..., _dispatch_options=...) instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return _original_apply_async(self, args, kwargs, **options)


def _intercepted_call(self, *args: Any, **kwargs: Any) -> Any:
    """Replacement for ``Task.__call__()`` that wraps execution in an airlock scope.

    This ensures that any ``.delay()`` calls made during task execution are
    intercepted and buffered, with flush on success and discard on exception.
    """
    with airlock.scope(policy=AllowAll()):
        return _original_call(self, *args, **kwargs)


def install_global_intercept(
    app: "Celery | None" = None,
    *,
    wrap_task_execution: bool = True,
) -> None:
    """Install global interception of ``.delay()`` and ``.apply_async()`` calls.

    When a scope is active, all ``.delay()``/``.apply_async()`` calls are routed
    through ``airlock.enqueue()``. When no scope is active, calls emit a
    deprecation warning and pass through normally.

    With ``wrap_task_execution=True`` (default), task execution is also wrapped
    in an airlock scope. This means:

    - Tasks automatically get an airlock scope
    - Any ``.delay()`` calls within tasks are intercepted and buffered
    - On task success: buffered intents flush
    - On task exception: buffered intents are discarded

    This is a monkey-patch. Call it once at app startup, after Celery is
    configured but before tasks are invoked.

    Example::

        # celery.py or conftest.py
        from airlock.integrations.celery import install_global_intercept

        app = Celery(...)
        install_global_intercept(app)

        # Or without execution wrapping (only intercept .delay() calls):
        install_global_intercept(app, wrap_task_execution=False)

    Args:
        app: Optional Celery app. Currently unused but reserved for future
            per-app scoping.
        wrap_task_execution: If ``True`` (default), wrap ``Task.__call__`` in an
            airlock scope so tasks automatically buffer and flush effects.

    Raises:
        RuntimeError: If called more than once.
    """
    global _original_delay, _original_apply_async, _original_call, _installed, _wrap_execution

    if _installed:
        raise RuntimeError(
            "install_global_intercept() has already been called. "
            "It should only be called once at app startup."
        )

    # Store originals
    _original_delay = Task.delay
    _original_apply_async = Task.apply_async

    # Patch .delay() and .apply_async()
    Task.delay = _intercepted_delay
    Task.apply_async = _intercepted_apply_async

    # Optionally wrap task execution
    if wrap_task_execution:
        _original_call = Task.__call__
        Task.__call__ = _intercepted_call
        _wrap_execution = True

    _installed = True


def uninstall_global_intercept() -> None:
    """Remove global interception. Mainly for testing."""
    global _original_delay, _original_apply_async, _original_call, _installed, _wrap_execution

    if not _installed:
        return

    Task.delay = _original_delay
    Task.apply_async = _original_apply_async

    if _wrap_execution:
        Task.__call__ = _original_call
        _wrap_execution = False

    _original_delay = None
    _original_apply_async = None
    _original_call = None
    _installed = False
