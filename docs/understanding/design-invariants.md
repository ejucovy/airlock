# Design Invariants

These are the core guarantees that airlock enforces by design.

## 1. Policies cannot enqueue

Calling `enqueue()` from within a policy raises `PolicyEnqueueError`.

Policies observe and filter — they don't produce new side effects. This keeps the system predictable: the set of intents comes from your domain code, not from policy logic.

## 2. Buffered effects escape only at flush

Effects enqueued via `airlock.enqueue()` are held in the buffer until the scope flushes. There's no way for them to escape early — no "force dispatch" API, no automatic leaking.

This is the control airlock provides: you express intent anywhere in your code, but the scope boundary decides when (and whether) those effects actually run.

## 3. No scope = error

Calling `enqueue()` outside a scope raises `NoScopeError`.

This is intentional. Airlock requires explicit lifecycle boundaries — side effects should not escape silently. If you want auto-dispatch without a scope, just call `.delay()` directly. The strictness is a feature, not a limitation.

## 4. Concurrent units of work have isolated scopes

Each request, task, or concurrent greenlet has its own scope context. Scopes cannot leak across concurrent execution boundaries.

Airlock uses Python's `contextvars` module for scope storage. This provides automatic isolation for:

- **Threads**: Each thread has its own context
- **asyncio tasks**: Each task has its own context copy
- **Processes**: Separate memory, naturally isolated
- **Greenlets** (gevent/eventlet): Each greenlet has its own context (requires greenlet >= 1.0)

### Greenlet requirement

If you use gevent, eventlet, or other greenlet-based concurrency, you must have **greenlet >= 1.0** installed. This version added native `contextvars` support, ensuring each greenlet has isolated context.

Airlock checks for this at import time and emits a `RuntimeWarning` if an older greenlet is detected:

```
RuntimeWarning: Detected greenlet without contextvars support.
airlock requires greenlet>=1.0 for correct isolation in gevent/eventlet environments.
```

Modern versions of gevent (20.9.0+) and eventlet already require greenlet >= 1.0, so this should only affect very old installations.

To verify your environment is safe:

```python
import greenlet
assert getattr(greenlet, "GREENLET_USE_CONTEXT_VARS", False), "Upgrade greenlet!"
```
