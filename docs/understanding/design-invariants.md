# Design Invariants

These are the core guarantees that airlock enforces by design.

## 1. Policies cannot enqueue

Calling `enqueue()` from within a policy raises `PolicyEnqueueError`.

Policies observe and filter — they don't produce new side effects. This keeps the system predictable: the set of intents comes from your domain code, not from policy logic.

## 2. Side effects escape in one place

Only scope flush dispatches effects. No `.delay()` calls scattered through domain code.

This is the whole point: express intent anywhere, but control the exit. If you're calling `.delay()` directly, you don't need airlock.

## 3. No scope = error

Calling `enqueue()` outside a scope raises `NoScopeError`.

This is intentional. Airlock requires explicit lifecycle boundaries — side effects should not escape silently. If you want auto-dispatch without a scope, just call `.delay()` directly. The strictness is a feature, not a limitation.
