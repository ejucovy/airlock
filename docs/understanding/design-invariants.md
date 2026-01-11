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
