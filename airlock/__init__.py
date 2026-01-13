"""
airlock - Policy-controlled lifecycle boundary for side effects.

Buffer side effects. Control what escapes.

Usage:
    import airlock

    def do_stuff():
        airlock.enqueue(send_email, user_id=123)

    with airlock.scope(policy=airlock.DropAll()):
        do_stuff()  # nothing escapes
"""

from contextvars import ContextVar, Token
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Protocol, Iterator, runtime_checkable
import logging
import warnings

__version__ = "0.1.0"


# ============================================================================
# Greenlet Compatibility Check
# ============================================================================


def _check_greenlet_compatibility() -> None:
    """
    Warn if running with an old greenlet that doesn't support contextvars.

    greenlet >= 1.0 natively supports contextvars, providing per-greenlet
    isolation. Older versions share contextvars across greenlets, which would
    cause scope leakage in concurrent environments like gevent or eventlet.

    This check runs at import time to provide early warning.
    """
    try:
        import greenlet
    except ImportError:
        # No greenlet installed - not a greenlet-based environment
        return

    if not getattr(greenlet, "GREENLET_USE_CONTEXT_VARS", False):
        warnings.warn(
            "Detected greenlet without contextvars support. "
            "airlock requires greenlet>=1.0 for correct isolation in "
            "gevent/eventlet environments. Without this, concurrent "
            "requests or tasks may leak scope state. "
            "Upgrade with: pip install 'greenlet>=1.0'",
            RuntimeWarning,
            stacklevel=2,
        )


_check_greenlet_compatibility()


# ============================================================================
# Configuration
# ============================================================================

# Global configuration for scope defaults
_config: dict[str, Any] = {
    "scope_cls": None,  # None means use Scope (can't reference it yet)
    "policy": None,     # None means use AllowAll()
    "executor": None,   # None means use default sync executor
}


def configure(
    *,
    scope_cls: "type[Scope] | None" = None,
    policy: "Policy | None" = None,
    executor: "Executor | None" = None,
) -> None:
    """
    Configure global defaults for airlock scopes.

    Call this once at application startup to set defaults that apply to
    all `scope()` and `scoped()` calls. Explicit arguments to `scope()`/`scoped()`
    always override these defaults.

    Args:
        scope_cls: Default `Scope` class. Use this to set `DjangoScope` as the
            default in Django applications.
        policy: Default policy for all scopes.
        executor: Default executor for all scopes.

    Example:
        In Django, this is called automatically by `AppConfig.ready()`
        if you add ``airlock.integrations.django`` to ``INSTALLED_APPS``.

        Manual configuration::

            from airlock import configure, Scope
            from airlock.integrations.django import DjangoScope

            configure(scope_cls=DjangoScope)

    Note:
        Configuration is stored globally. In tests, use `reset_configuration()`
        to restore defaults between tests.
    """
    if scope_cls is not None:
        _config["scope_cls"] = scope_cls
    if policy is not None:
        _config["policy"] = policy
    if executor is not None:
        _config["executor"] = executor


def reset_configuration() -> None:
    """Reset configuration to defaults. Primarily for testing."""
    _config["scope_cls"] = None
    _config["policy"] = None
    _config["executor"] = None


def get_configuration() -> dict[str, Any]:
    """Get current configuration. Primarily for testing/debugging.

    Returns a copy to prevent mutation.
    """
    return dict(_config)


# ============================================================================
# Context
# ============================================================================

_current_scope: ContextVar["Scope | None"] = ContextVar(
    "airlock_current_scope",
    default=None,
)

_in_policy: ContextVar[bool] = ContextVar(
    "airlock_in_policy",
    default=False,
)

_policy_stack: ContextVar[tuple["Policy", ...]] = ContextVar(
    "airlock_policy_stack",
    default=(),
)


def get_current_scope() -> "Scope | None":
    """Get the currently active airlock scope, if any."""
    return _current_scope.get()


# ============================================================================
# Intent
# ============================================================================


@dataclass(frozen=True)
class Intent:
    """Represents the intent to perform a side effect.

    Stores the actual callable, not just a name. The `name` property
    derives a string for serialization/logging.

    Captures local policy context at enqueue time for introspection
    and deferred application at flush.
    """

    task: Callable
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    origin: str | None = None
    dispatch_options: dict[str, Any] | None = None
    _local_policies: tuple["Policy", ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.args, tuple):
            object.__setattr__(self, "args", tuple(self.args))

    @property
    def name(self) -> str:
        """Derived name for serialization/logging."""
        # Celery tasks have a .name attribute
        if hasattr(self.task, "name"):
            return self.task.name
        # Regular functions - use qualified name
        module = getattr(self.task, "__module__", "<unknown>")
        qualname = getattr(self.task, "__qualname__", str(self.task))
        return f"{module}:{qualname}"

    # NOTE: Intentionally not hashable. kwargs and dispatch_options may contain
    # unhashable values, and identity semantics suffice for airlock's purposes.
    # If you need to dedupe intents, use explicit identity comparison.
    __hash__ = None  # type: ignore[assignment]

    def __str__(self) -> str:
        """User-friendly string showing the task call signature."""
        parts = [repr(a) for a in self.args]
        parts.extend(f"{k}={v!r}" for k, v in self.kwargs.items())
        args_str = ", ".join(parts)
        return f"{self.name}({args_str})"

    def __repr__(self) -> str:
        origin_str = f", origin={self.origin!r}" if self.origin else ""
        opts_str = f", dispatch_options={self.dispatch_options!r}" if self.dispatch_options else ""
        policies_str = f", policies={len(self._local_policies)}" if self._local_policies else ""
        return f"Intent({self.name!r}, args={self.args!r}, kwargs={self.kwargs!r}{origin_str}{opts_str}{policies_str})"

    @property
    def local_policies(self) -> tuple["Policy", ...]:
        """Local policies captured at enqueue time."""
        return self._local_policies

    def passes_local_policies(self) -> bool:
        """Check if this intent passes its captured local policies.

        Returns:
            True if all local policies allow this intent.

        Note:
            This does NOT guarantee the intent will be dispatched. It does not
            consider:

            - Scope-level policy (checked separately at flush)
            - Whether the scope flushes or discards
            - Dispatch execution success

            Use for inspection and audit, not execution prediction.
        """
        for p in reversed(self._local_policies):
            if not p.allows(self):
                return False
        return True


# ============================================================================
# Executor Protocol
# ============================================================================


@runtime_checkable
class Executor(Protocol):
    """Protocol for intent executors.

    An executor is a callable that takes an `Intent` and executes it
    via some dispatch mechanism (synchronous, Celery, django-q, etc.).

    Built-in executors are available in ``airlock.integrations.executors``:

    - ``sync_executor``: Synchronous execution (default)
    - ``celery_executor``: Dispatch via Celery ``.delay()`` / ``.apply_async()``
    - ``django_q_executor``: Dispatch via django-q's ``async_task()``
    - ``django_tasks_executor``: Dispatch via Django 6+'s built-in tasks framework
    - ``huey_executor``: Dispatch via Huey's ``.schedule()``
    - ``dramatiq_executor``: Dispatch via Dramatiq's ``.send()``

    Custom executors can be written by implementing this protocol.
    """

    def __call__(self, intent: Intent) -> None:
        """Execute the given intent."""
        ...


# ============================================================================
# Errors
# ============================================================================


class AirlockError(Exception):
    """Base exception for all airlock errors."""

    pass


class UsageError(AirlockError):
    """Raised when airlock is used incorrectly (API misuse)."""

    pass


class PolicyEnqueueError(UsageError):
    """Raised when `enqueue()` is called from within a policy callback."""

    pass


class NoScopeError(UsageError):
    """Raised when `enqueue()` is called with no active scope.

    This is intentional: airlock requires explicit lifecycle boundaries.
    Side effects should not escape silently. Every `enqueue()` must occur
    within a `scope()` that decides when (and whether) effects dispatch.

    If you're seeing this error, wrap your code in an `airlock.scope()`::

        with airlock.scope():
            do_stuff()  # enqueue() calls are now valid
    """

    pass


class ScopeStateError(AirlockError):
    """Raised when an operation is invalid for the scope's current lifecycle state."""

    pass


class PolicyViolation(AirlockError):
    """Raised when a policy explicitly rejects an intent."""

    pass


# ============================================================================
# Policy
# ============================================================================


@runtime_checkable
class Policy(Protocol):
    """Protocol for side effect policies.

    Policies are per-intent boolean gates that decide which intents dispatch.
    This design enforces FIFO order by construction - policies can filter
    intents but cannot reorder them.

    Methods:
        on_enqueue: Called when an intent is added to the buffer. Use for
            observation, logging, or raising `PolicyViolation` for hard blocks.
        allows: Called at flush time for each intent. Return ``True`` to dispatch,
            ``False`` to silently drop.
    """

    def on_enqueue(self, intent: Intent) -> None:
        """Called when an intent is added to the buffer. Observe or raise `PolicyViolation`."""
        ...

    def allows(self, intent: Intent) -> bool:
        """Called at flush time. Return ``True`` to dispatch, ``False`` to drop."""
        ...


class AllowAll:
    """Policy that allows all side effects."""

    def on_enqueue(self, intent: Intent) -> None:
        pass

    def allows(self, intent: Intent) -> bool:
        return True

    def __repr__(self) -> str:
        return "AllowAll()"


class DropAll:
    """Policy that drops all side effects."""

    def on_enqueue(self, intent: Intent) -> None:
        pass

    def allows(self, intent: Intent) -> bool:
        return False

    def __repr__(self) -> str:
        return "DropAll()"


class AssertNoEffects:
    """Policy that raises if any side effect is attempted."""

    def on_enqueue(self, intent: Intent) -> None:
        raise PolicyViolation(
            f"Unexpected side effect: {intent.name}. "
            f"No side effects are allowed in this scope."
        )

    def allows(self, intent: Intent) -> bool:
        return False  # Unreachable - on_enqueue always raises

    def __repr__(self) -> str:
        return "AssertNoEffects()"


class BlockTasks:
    """Policy that blocks specific tasks by name."""

    def __init__(
        self,
        blocked: set[str],
        *,
        raise_on_enqueue: bool = False,
    ) -> None:
        self._blocked = frozenset(blocked)
        self._raise_on_enqueue = raise_on_enqueue

    def on_enqueue(self, intent: Intent) -> None:
        if self._raise_on_enqueue and intent.name in self._blocked:
            raise PolicyViolation(
                f"Task '{intent.name}' is blocked and cannot be enqueued."
            )

    def allows(self, intent: Intent) -> bool:
        return intent.name not in self._blocked

    def __repr__(self) -> str:
        raise_str = ", raise_on_enqueue=True" if self._raise_on_enqueue else ""
        return f"BlockTasks({set(self._blocked)!r}{raise_str})"


class LogOnFlush:
    """Policy that logs intents at flush time (allows all)."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger("airlock")

    def on_enqueue(self, intent: Intent) -> None:
        pass

    def allows(self, intent: Intent) -> bool:
        self._logger.info(
            "Flushing intent: %s(args=%r, kwargs=%r)",
            intent.name,
            intent.args,
            intent.kwargs,
        )
        return True

    def __repr__(self) -> str:
        return f"LogOnFlush(logger={self._logger.name!r})"


class CompositePolicy:
    """Policy that combines multiple policies (all must allow)."""

    def __init__(self, *policies: Policy) -> None:
        self._policies = policies

    def on_enqueue(self, intent: Intent) -> None:
        for policy in self._policies:
            policy.on_enqueue(intent)

    def allows(self, intent: Intent) -> bool:
        return all(policy.allows(intent) for policy in self._policies)

    def __repr__(self) -> str:
        policies_str = ", ".join(repr(p) for p in self._policies)
        return f"CompositePolicy({policies_str})"


# ============================================================================
# Scope
# ============================================================================


def _execute(intent: Intent) -> None:
    """
    Default executor: synchronous execution, ignoring dispatch_options.
    """
    intent.task(*intent.args, **intent.kwargs)


class Scope:
    """A lifecycle scope that buffers and controls side effect intents.

    Args:
        policy: Policy controlling what intents are allowed.
        executor: Callable that executes intents. Defaults to synchronous execution.
            See ``airlock.integrations.executors`` for available executors.
    """

    def __init__(
        self,
        policy: Policy,
        executor: Executor | None = None
    ) -> None:
        self._policy = policy
        self._executor = executor or _execute
        self._intents: list[Intent] = []
        self._flushed = False
        self._discarded = False
        self._token: Token | None = None
        self._parent: "Scope | None" = None
        self._captured_intents: list[Intent] = []
        self._own_intents_cache: list[Intent] | None = None

    @property
    def intents(self) -> list[Intent]:
        """Read-only access to buffered intents for inspection."""
        return list(self._intents)

    @property
    def is_flushed(self) -> bool:
        return self._flushed

    @property
    def is_discarded(self) -> bool:
        return self._discarded

    @property
    def is_active(self) -> bool:
        """True if this scope is currently the active scope."""
        return self._token is not None and _current_scope.get() is self

    @property
    def captured_intents(self) -> list[Intent]:
        """Intents captured from nested scopes."""
        return list(self._captured_intents)

    @property
    def own_intents(self) -> list[Intent]:
        """Intents enqueued directly in this scope (not captured from nested scopes)."""
        if self._own_intents_cache is None:
            captured_set = set(id(i) for i in self._captured_intents)
            self._own_intents_cache = [i for i in self._intents if id(i) not in captured_set]
        return list(self._own_intents_cache)

    def enter(self) -> "Scope":
        """Activate this scope.

        Sets the context var so `enqueue()` routes intents to this scope.
        Must call `exit()` when done, before calling `flush()` or `discard()`.

        Returns:
            Self for chaining.

        Raises:
            ScopeStateError: If this scope is already active.
        """
        if self._token is not None:
            raise ScopeStateError("Scope is already active.")

        # Capture parent scope before activating
        self._parent = _current_scope.get()

        self._token = _current_scope.set(self)
        return self

    def exit(self) -> None:
        """Deactivate this scope.

        Resets the context var to the previous scope (or ``None``).
        Must be called before `flush()` or `discard()`.

        Raises:
            ScopeStateError: If this scope is not active.
        """
        if self._token is None:
            raise ScopeStateError("Scope is not active.")
        _current_scope.reset(self._token)
        self._token = None

    def should_flush(self, error: BaseException | None) -> bool:
        """Decide terminal action when context manager exits.

        Override this method in subclasses to customize flush/discard behavior.

        Args:
            error: The exception that caused exit, or ``None`` for normal exit.

        Returns:
            ``True`` to flush (dispatch intents), ``False`` to discard.

        Default behavior: flush on success, discard on error.
        """
        return error is None

    def before_descendant_flushes(self, exiting_scope: "Scope", intents: list[Intent]) -> list[Intent]:
        """Called when a nested scope exits and attempts to flush.

        This method is called during the parent chain walk, allowing each ancestor
        to decide which intents the exiting scope may flush vs which to capture.

        Args:
            exiting_scope: The nested scope that is exiting (may be deeply nested).
            intents: The list of intents the exiting scope wants to flush.

        Returns:
            list[Intent]: The list of intents to allow through (the exiting scope will
                flush these). Any intents not in the returned list are captured into
                this scope's buffer. **Important**: Must return a list; returning
                ``None`` or other types raises ``TypeError``.

        Raises:
            TypeError: If return value is not a list. Any other exception raised by
                this method will propagate and abort the flush, potentially leaving
                the scope in a partially-modified state.

        Default behavior: Capture all intents (return ``[]``).
        This is the controlled default - outer scopes have authority over nested scopes.

        Override this method to allow nested scopes to flush independently:

        - Return ``[]`` to capture all intents (default, controlled)
        - Return ``intents`` to allow all (independent nested scopes)
        - Return filtered list to selectively capture

        Note:
            - Do not mutate the ``intents`` list. Return a new list or slice.
            - Returning intents not in the input list has undefined behavior.
            - In multi-level nesting, ``exiting_scope`` is always the innermost scope,
              not necessarily the immediate child. Intermediate scopes haven't exited yet.

        Example::

            class IndependentScope(Scope):
                def before_descendant_flushes(self, exiting_scope, intents):
                    return intents  # Allow nested scopes to flush independently

            class SmartScope(Scope):
                def before_descendant_flushes(self, exiting_scope, intents):
                    # Capture dangerous tasks, allow safe ones
                    return [i for i in intents if 'dangerous' not in i.name]
        """
        return []  # Controlled default: capture everything

    def _add(self, intent: Intent) -> None:
        """Add an intent to the buffer. Internal - use `enqueue()` instead."""
        if self._flushed or self._discarded:
            raise ScopeStateError(
                f"Cannot add intents to a scope that has been "
                f"{'flushed' if self._flushed else 'discarded'}."
            )

        # INVARIANT: Policies do not enqueue
        token = _in_policy.set(True)
        try:
            self._policy.on_enqueue(intent)
        finally:
            _in_policy.reset(token)

        self._intents.append(intent)
        self._own_intents_cache = None  # Invalidate cache

    def flush(self) -> list[Intent]:
        """Flush all buffered intents - apply policy and dispatch.

        Filters intents through policies (both local and scope-level), then dispatches
        them in FIFO order using the configured executor.

        Returns:
            List of intents that were dispatched (after policy filtering).

        Raises:
            ScopeStateError: If scope is already flushed, discarded, or still active.
            Exception: Any exception raised by the executor during dispatch (fail-fast
                behavior). See `_dispatch_all()` docstring for details on exception
                handling.

        Note:
            The scope is marked as flushed even if an executor raises an exception.
            This prevents retry attempts, as the scope is in an inconsistent state
            (some intents may have been dispatched before the failure).
        """
        if self._flushed:
            raise ScopeStateError("Scope has already been flushed.")
        if self._discarded:
            raise ScopeStateError("Cannot flush a discarded scope.")
        if self.is_active:
            raise ScopeStateError(
                "Cannot flush() while scope is still active. "
                "Call exit() first."
            )

        self._flushed = True

        # Walk up parent chain to get approval for flushing
        intents_allowed_to_flush = self._walk_parent_chain_for_approval(self._intents)

        token = _in_policy.set(True)
        try:
            # Filter intents through policies (FIFO order preserved)
            intents_to_dispatch = []
            for intent in intents_allowed_to_flush:
                # First: check local policies (innermost first)
                allowed = True
                for local_policy in reversed(intent._local_policies):
                    if not local_policy.allows(intent):
                        allowed = False
                        break

                # Second: check scope policy
                if allowed and self._policy.allows(intent):
                    intents_to_dispatch.append(intent)
        finally:
            _in_policy.reset(token)

        # Dispatch in FIFO order
        self._dispatch_all(intents_to_dispatch)

        return intents_to_dispatch

    def _walk_parent_chain_for_approval(self, intents: list[Intent]) -> list[Intent]:
        """Walk up the parent chain, calling `before_descendant_flushes` on each parent.

        Each parent decides which intents this scope is allowed to flush.
        Intents not approved are captured into the parent's buffer.

        Returns:
            The list of intents that survived all parent approvals.
        """
        if self._parent is None:
            # No parent - we're the root scope, can flush everything
            return intents

        current_intents = intents
        parent = self._parent

        # Walk up the chain
        while parent is not None:
            # Ask parent what it allows us to flush
            allowed = parent.before_descendant_flushes(self, current_intents)

            # Validate return value
            if not isinstance(allowed, list):
                raise TypeError(
                    f"before_descendant_flushes() must return a list, got {type(allowed).__name__}"
                )

            # Parent captures what it didn't allow
            # Use id-based set for O(n) instead of O(n²) list membership check
            allowed_ids = {id(i) for i in allowed}
            captured = [i for i in current_intents if id(i) not in allowed_ids]

            if captured:
                parent._captured_intents.extend(captured)
                parent._intents.extend(captured)
                parent._own_intents_cache = None  # Invalidate cache

            # Continue up the chain with only allowed intents
            current_intents = allowed
            parent = parent._parent

        return current_intents

    def _dispatch_all(self, intents: list[Intent]) -> None:
        """Dispatch intents using the configured executor.

        Subclasses may override to customize dispatch timing (e.g., defer to
        ``on_commit``). The executor itself determines HOW intents are executed
        (sync, Celery, django-q, etc.).

        Exception behavior (fail-fast):
            If an executor raises an exception while dispatching an intent, the
            exception propagates immediately and remaining intents in the queue
            are NOT dispatched. This is intentional - executor failures are out
            of scope.

            Example::

                with scope():
                    enqueue(task_a)  # succeeds
                    enqueue(task_b)  # executor raises during flush
                    enqueue(task_c)  # will NOT execute

                # task_a executes successfully
                # task_b raises exception (e.g., broker connection failure)
                # task_c is never attempted (fail-fast)

            For async executors (Celery, django-q, etc.), dispatch exceptions are
            rare - they typically only occur when the broker/queue is unreachable.
            The actual task execution happens asynchronously, so task failures are
            not visible here.
        """
        for intent in intents:
            self._executor(intent)

    def discard(self) -> list[Intent]:
        """Discard all buffered intents without dispatching."""
        if self._discarded:
            raise ScopeStateError("Scope has already been discarded.")
        if self._flushed:
            raise ScopeStateError("Cannot discard a flushed scope.")
        if self.is_active:
            raise ScopeStateError(
                "Cannot discard() while scope is still active. "
                "Call exit() first."
            )

        self._discarded = True
        discarded = list(self._intents)
        self._intents.clear()
        return discarded


@contextmanager
def scope(
    policy: Policy | None = None,
    *,
    _cls: type[Scope] | None = None,
    **kwargs,
) -> Iterator[Scope]:
    """Context manager defining a lifecycle boundary for side effects.

    Args:
        policy: Policy controlling what intents are allowed. Defaults to configured
            policy or `AllowAll` if not configured.
        _cls: `Scope` class to use. Defaults to configured ``scope_cls`` or `Scope`
            if not configured. Subclass `Scope` and override `should_flush()` to
            customize flush/discard behavior.
        **kwargs: Additional arguments passed to `Scope` constructor (e.g., executor).

    Keyword Args:
        executor: Callable that executes intents. Defaults to configured executor
            or synchronous execution if not configured.
            See ``airlock.integrations.executors`` for available executors.

    Behavior:
        - On normal exit: calls `flush()` if `should_flush(None)` returns ``True``
        - On exception: calls `flush()` if `should_flush(error)` returns ``True``,
          else `discard()`

    The default `Scope.should_flush()` returns ``True`` on success, ``False`` on error.
    Subclass `Scope` to customize this behavior.

    Note:
        Arguments passed explicitly always override configured defaults.
        Use `airlock.configure()` to set application-wide defaults.

    Example::

        # Use celery executor
        from airlock.integrations.executors.celery import celery_executor
        with airlock.scope(executor=celery_executor):
            airlock.enqueue(my_task, ...)

        # Use django-q executor
        from airlock.integrations.executors.django_q import django_q_executor
        with airlock.scope(executor=django_q_executor):
            airlock.enqueue(my_task, ...)
    """
    # Apply configured defaults for anything not explicitly provided
    actual_cls = _cls if _cls is not None else (_config["scope_cls"] or Scope)
    actual_policy = policy if policy is not None else (_config["policy"] or AllowAll())

    # For executor, check if it's in kwargs; if not, use configured default
    if "executor" not in kwargs and _config["executor"] is not None:
        kwargs["executor"] = _config["executor"]

    s = actual_cls(policy=actual_policy, **kwargs)
    s.enter()

    error: BaseException | None = None
    try:
        yield s
    except BaseException as e:
        error = e
        raise
    finally:
        s.exit()

        if not s.is_flushed and not s.is_discarded:
            if s.should_flush(error):
                s.flush()
            else:
                s.discard()


def scoped(
    policy: Policy | None = None,
    *,
    _cls: type[Scope] | None = None,
    **kwargs,
) -> Callable[[Callable], Callable]:
    """Decorator that wraps a function in an airlock scope.

    This is a convenience for wrapping task functions, command handlers,
    or any callable that should run inside a scope.

    Args:
        policy: Policy controlling what intents are allowed. Defaults to configured
            policy or `AllowAll` if not configured.
        _cls: `Scope` class to use. Defaults to configured ``scope_cls`` or `Scope`
            if not configured. Subclass `Scope` and override `should_flush()` to
            customize flush/discard behavior.
        **kwargs: Additional arguments passed to `Scope` constructor (e.g., executor).

    Example::

        @airlock.scoped()
        def my_task():
            airlock.enqueue(send_email, user_id=123)

        # With Celery
        @app.task
        @airlock.scoped()
        def my_celery_task():
            airlock.enqueue(another_task, ...)

        # With custom policy
        @airlock.scoped(policy=MyPolicy())
        def my_task():
            ...

    Behavior:
        - On normal return: flushes the scope (dispatches intents)
        - On exception: discards the scope (drops intents)

    Note:
        The decorator creates a fresh scope for each invocation. This is
        safe for concurrent execution - each call gets its own isolated scope.
        Arguments passed explicitly always override configured defaults.
    """
    from functools import wraps

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kw):
            with scope(policy=policy, _cls=_cls, **kwargs):
                return func(*args, **kw)
        return wrapper

    return decorator


# ============================================================================
# Local Policy Context
# ============================================================================


@contextmanager
def policy(p: Policy) -> Iterator[None]:
    """Context manager for local policy contexts.

    Intents enqueued within this context capture the policy and apply it
    at flush time. This enables local control without nested buffers.

    Example::

        with airlock.scope():
            airlock.enqueue(task_a)  # will dispatch

            with airlock.policy(DropAll()):
                airlock.enqueue(task_b)  # will NOT dispatch

            airlock.enqueue(task_c)  # will dispatch

    Unlike nested scopes, all intents go to the same buffer. The local
    policy is metadata that affects dispatch decisions at flush.

    Note:
        This does NOT create a new buffer or nested scope. All intents
        from within this context still go to the enclosing scope's buffer.
        The policy is captured on each intent at enqueue time and evaluated
        at flush. This is intentional - it preserves a single dispatch boundary
        while allowing fine-grained control over which intents survive.
    """
    current_stack = _policy_stack.get()
    new_stack = current_stack + (p,)
    token = _policy_stack.set(new_stack)
    try:
        yield
    finally:
        _policy_stack.reset(token)


# ============================================================================
# enqueue
# ============================================================================


def enqueue(
    task: Callable,
    *args: Any,
    _origin: str | None = None,
    _dispatch_options: dict[str, Any] | None = None,
    **kwargs: Any,
) -> None:
    """Express intent to perform a side effect.

    This is the ONLY function domain code should call.

    Args:
        task: The callable to execute (Celery task, function, etc.).
        *args: Positional arguments for the task.
        _origin: Optional origin metadata for debugging/observability.
            This is NOT auto-detected - it must be set explicitly if needed.
            Integrations (Django middleware, Celery task wrapper) may set this
            to provide context like request path, task name, or trace/span IDs.
            For structured observability, prefer OpenTelemetry span context.
        _dispatch_options: Optional dispatch options (countdown, queue, etc.).
            Passed through to the task queue backend (e.g., Celery's ``apply_async``).
            Ignored for plain callables.
        **kwargs: Keyword arguments for the task.

    Raises:
        PolicyEnqueueError: If called from within a policy callback.
        NoScopeError: If no scope is active.
        PolicyViolation: If a policy explicitly rejects the intent via `on_enqueue()`.
            For example, `AssertNoEffects` policy raises `PolicyViolation` on any
            enqueue. When this happens, the intent is NOT added to the buffer.
    """
    # INVARIANT: Policies do not enqueue
    if _in_policy.get():
        raise PolicyEnqueueError(
            "Cannot call enqueue() from within a policy callback. "
            "Policies may judge intents, but must not create them."
        )

    # Capture local policy stack immutably.
    # IMPORTANT: Local policies are metadata, not control flow.
    # They do NOT affect buffering or ordering, only dispatch decisions at flush.
    # This immutable capture means the intent records "what policies were active
    # when I was enqueued", enabling introspection via intent.passes_local_policies().
    local_policies = _policy_stack.get()

    intent = Intent(
        task=task,
        args=args,
        kwargs=kwargs,
        origin=_origin,
        dispatch_options=_dispatch_options,
        _local_policies=local_policies,
    )

    current_scope = _current_scope.get()
    if current_scope is not None:
        current_scope._add(intent)
    else:
        raise NoScopeError(
            f"Cannot enqueue '{intent.name}' without an active airlock.scope(). "
            f"Wrap your code in an airlock.scope() context manager."
        )


# ============================================================================
# Exports
# ============================================================================

__all__ = [
    # Configuration
    "configure",
    "reset_configuration",
    "get_configuration",
    # Core
    "Intent",
    "Executor",
    "enqueue",
    "scope",
    "scoped",
    "policy",
    "Scope",
    "get_current_scope",
    # Errors
    "AirlockError",
    "UsageError",
    "PolicyEnqueueError",
    "NoScopeError",
    "ScopeStateError",
    "PolicyViolation",
    # Policies
    "Policy",
    "AllowAll",
    "DropAll",
    "AssertNoEffects",
    "BlockTasks",
    "LogOnFlush",
    "CompositePolicy",
    # Internal (for integrations)
    "_execute",
    "_current_scope",
    "_in_policy",
]
