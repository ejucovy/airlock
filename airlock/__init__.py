"""
airlock - Policy-controlled lifecycle boundary for side effects.

Buffer side effects. Control what escapes. ~200 lines.

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

__version__ = "0.1.0"


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
    """
    Represents the intent to perform a side effect.

    Stores the actual callable, not just a name. The name property
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
        """
        Check if this intent passes its captured local policies.

        Returns True if all local policies allow this intent.

        NOTE: This does NOT guarantee the intent will be dispatched. It does not consider:
          - scope-level policy (checked separately at flush)
          - whether the scope flushes or discards
          - dispatch execution success

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
    """
    Protocol for intent executors.

    An executor is a callable that takes an Intent and executes it
    via some dispatch mechanism (synchronous, Celery, django-q, etc.).

    Built-in executors are available in airlock.integrations.executors:
    - sync_executor: Synchronous execution (default)
    - celery_executor: Dispatch via Celery .delay() / .apply_async()
    - django_q_executor: Dispatch via django-q's async_task()
    - huey_executor: Dispatch via Huey's .schedule()
    - dramatiq_executor: Dispatch via Dramatiq's .send()

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
    """Raised when enqueue() is called from within a policy callback."""

    pass


class NoScopeError(UsageError):
    """
    Raised when enqueue() is called with no active scope.

    This is intentional: airlock requires explicit lifecycle boundaries.
    Side effects should not escape silently. Every enqueue() must occur
    within a scope() that decides when (and whether) effects dispatch.

    If you're seeing this error, wrap your code in an airlock.scope():

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
    """
    Protocol for side effect policies.

    Policies are per-intent boolean gates that decide which intents dispatch.
    This design enforces FIFO order by construction - policies can filter
    intents but cannot reorder them.

    Methods:
        on_enqueue: Called when an intent is added to the buffer. Use for
            observation, logging, or raising PolicyViolation for hard blocks.
        allows: Called at flush time for each intent. Return True to dispatch,
            False to silently drop.
    """

    def on_enqueue(self, intent: Intent) -> None:
        """Called when an intent is added to the buffer. Observe or raise."""
        ...

    def allows(self, intent: Intent) -> bool:
        """Called at flush time. Return True to dispatch, False to drop."""
        ...


class AllowAll:
    """Policy that allows all side effects."""

    def on_enqueue(self, intent: Intent) -> None:
        pass

    def allows(self, intent: Intent) -> bool:
        return True


class DropAll:
    """Policy that drops all side effects."""

    def on_enqueue(self, intent: Intent) -> None:
        pass

    def allows(self, intent: Intent) -> bool:
        return False


class AssertNoEffects:
    """Policy that raises if any side effect is attempted."""

    def on_enqueue(self, intent: Intent) -> None:
        raise PolicyViolation(
            f"Unexpected side effect: {intent.name}. "
            f"No side effects are allowed in this scope."
        )

    def allows(self, intent: Intent) -> bool:
        return False  # Unreachable - on_enqueue always raises


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


class CompositePolicy:
    """Policy that combines multiple policies (all must allow)."""

    def __init__(self, *policies: Policy) -> None:
        self._policies = policies

    def on_enqueue(self, intent: Intent) -> None:
        for policy in self._policies:
            policy.on_enqueue(intent)

    def allows(self, intent: Intent) -> bool:
        return all(policy.allows(intent) for policy in self._policies)


# ============================================================================
# Scope
# ============================================================================


def _execute(intent: Intent) -> None:
    """
    Default executor: synchronous execution, ignoring dispatch_options.
    """
    intent.task(*intent.args, **intent.kwargs)


class Scope:
    """
    A lifecycle scope that buffers and controls side effect intents.

    Args:
        policy: Policy controlling what intents are allowed
        executor: Callable that executes intents. Defaults to synchronous execution.
            See airlock.integrations.executors for available executors.
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

    def enter(self) -> "Scope":
        """
        Activate this scope.

        Sets the context var so enqueue() routes intents to this scope.
        Must call exit() when done, before calling flush() or discard().

        Returns:
            self (for chaining)

        Raises:
            ScopeStateError: If this scope is already active.
        """
        if self._token is not None:
            raise ScopeStateError("Scope is already active.")
        self._token = _current_scope.set(self)
        return self

    def exit(self) -> None:
        """
        Deactivate this scope.

        Resets the context var to the previous scope (or None).
        Must be called before flush() or discard().

        Raises:
            ScopeStateError: If this scope is not active.
        """
        if self._token is None:
            raise ScopeStateError("Scope is not active.")
        _current_scope.reset(self._token)
        self._token = None

    def should_flush(self, error: BaseException | None) -> bool:
        """
        Decide terminal action when context manager exits.

        Override this method in subclasses to customize flush/discard behavior.

        Args:
            error: The exception that caused exit, or None for normal exit.

        Returns:
            True to flush (dispatch intents), False to discard.

        Default behavior: flush on success, discard on error.
        """
        return error is None

    def _add(self, intent: Intent) -> None:
        """Add an intent to the buffer. Internal - use enqueue() instead."""
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

    def flush(self) -> list[Intent]:
        """Flush all buffered intents - apply policy and dispatch."""
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

        token = _in_policy.set(True)
        try:
            # Filter intents through policies (FIFO order preserved)
            intents_to_dispatch = []
            for intent in self._intents:
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

    def _dispatch_all(self, intents: list[Intent]) -> None:
        """
        Dispatch intents using the configured executor.

        Subclasses may override to customize dispatch timing (e.g., defer to on_commit).
        The executor itself determines HOW intents are executed (sync, Celery, django-q, etc.).
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
    _cls: type[Scope] = Scope,
    **kwargs,
) -> Iterator[Scope]:
    """
    Context manager defining a lifecycle boundary for side effects.

    Args:
        policy: Policy controlling what intents are allowed. Defaults to AllowAll.
        _cls: Scope class to use. Subclass Scope and override should_flush()
            to customize flush/discard behavior.
        **kwargs: Additional arguments passed to Scope constructor (e.g., executor).

    Common kwargs:
        executor: Callable that executes intents. Defaults to synchronous execution.
            See airlock.integrations.executors for available executors.

    Behavior:
        - On normal exit: calls flush() if should_flush(None) returns True
        - On exception: calls flush() if should_flush(error) returns True, else discard()

    The default Scope.should_flush() returns True on success, False on error.
    Subclass Scope to customize this behavior.

    Examples:
        # Use celery executor
        from airlock.integrations.executors.celery import celery_executor
        with airlock.scope(executor=celery_executor):
            airlock.enqueue(my_task, ...)

        # Use django-q executor
        from airlock.integrations.executors.django_q import django_q_executor
        with airlock.scope(executor=django_q_executor):
            airlock.enqueue(my_task, ...)
    """
    if policy is None:
        policy = AllowAll()

    s = _cls(policy=policy, **kwargs)
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


# ============================================================================
# Local Policy Context
# ============================================================================


@contextmanager
def policy(p: Policy) -> Iterator[None]:
    """
    Context manager for local policy contexts.

    Intents enqueued within this context capture the policy and apply it
    at flush time. This enables local control without nested buffers.

    Example:
        with airlock.scope():
            airlock.enqueue(task_a)  # will dispatch

            with airlock.policy(DropAll()):
                airlock.enqueue(task_b)  # will NOT dispatch

            airlock.enqueue(task_c)  # will dispatch

    Unlike nested scopes, all intents go to the same buffer. The local
    policy is metadata that affects dispatch decisions at flush.

    NOTE: This does NOT create a new buffer or nested scope. All intents
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
    """
    Express intent to perform a side effect.

    This is the ONLY function domain code should call.

    Args:
        task: The callable to execute (Celery task, function, etc.)
        *args: Positional arguments for the task.
        _origin: Optional origin metadata for debugging/observability.
            This is NOT auto-detected - it must be set explicitly if needed.
            Integrations (Django middleware, Celery task wrapper) may set this
            to provide context like request path, task name, or trace/span IDs.
            For structured observability, prefer OpenTelemetry span context.
        _dispatch_options: Optional dispatch options (countdown, queue, etc.)
            Passed through to the task queue backend (e.g., Celery's apply_async).
            Ignored for plain callables.
        **kwargs: Keyword arguments for the task.

    Raises:
        PolicyEnqueueError: If called from within a policy callback.
        NoScopeError: If no scope is active.
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
    # Core
    "Intent",
    "Executor",
    "enqueue",
    "scope",
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
