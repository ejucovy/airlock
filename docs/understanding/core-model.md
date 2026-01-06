# Core Model: The 3 Concerns

Airlock separates three orthogonal concerns. Understanding this makes everything else obvious.

## The Three Concerns

| Concern | Controlled By | Question |
|---------|---------------|----------|
| **WHEN** | Scope | When do effects escape? |
| **WHAT** | Policy | Which effects execute? |
| **HOW** | Executor | How do they run? |

These are **independent** and can be mixed freely.

## Concern 1: WHEN (Scope)

**Scopes** control timing and lifecycle.

```python
# Basic scope: flush on success, discard on error
with airlock.scope():
    do_stuff()
    # Effects buffered...
# Effects execute here (on normal exit)
```

```python
# Transaction-aware scope: wait for commit
from airlock.integrations.django import DjangoScope

with transaction.atomic():
    with airlock.scope(_cls=DjangoScope):
        order.save()
        airlock.enqueue(send_email, order.id)
    # Effects still buffered...
# Effects execute here (after commit)
```

### Scope decides:
- When to flush (end of block, after commit, custom)
- Whether to flush (success vs error)
- How to store buffer (memory, database, etc.)

Default: flush on normal exit, discard on exception.

## Concern 2: WHAT (Policy)

**Policies** filter and observe intents.

```python
# Drop all effects (dry-run)
with airlock.scope(policy=airlock.DropAll()):
    process_orders()  # Effects buffered but never dispatched

# Assert no effects (testing)
with airlock.scope(policy=airlock.AssertNoEffects()):
    pure_function()  # Raises if any enqueue() called

# Block specific tasks
with airlock.scope(policy=airlock.BlockTasks({"send_email"})):
    process_order()  # Emails dropped, other tasks execute

# Log everything
with airlock.scope(policy=airlock.LogOnFlush(logger)):
    do_stuff()  # All dispatches logged
```

### Policy decides:
- Which intents are allowed (filter)
- What to observe (logging, metrics)
- When to fail fast (assertions)

Default: allow everything.

## Concern 3: HOW (Executor)

**Executors** control dispatch mechanism.

```python
# Sync execution (default)
with airlock.scope():
    airlock.enqueue(my_function, arg=123)
# Executes: my_function(arg=123)

# Celery
from airlock.integrations.executors.celery import celery_executor

with airlock.scope(executor=celery_executor):
    airlock.enqueue(celery_task, arg=123)
# Executes: celery_task.delay(arg=123)

# django-q
from airlock.integrations.executors.django_q import django_q_executor

with airlock.scope(executor=django_q_executor):
    airlock.enqueue(any_function, arg=123)
# Executes: async_task(any_function, arg=123)
```

### Executor decides:
- How to run the task (sync, queue, thread pool, lambda)
- What protocol to use (Celery, django-q, Huey, custom)

Default: synchronous execution.

## Mixing Concerns

The power is in composition:

```python
# Transaction-aware + Celery + logging
from airlock.integrations.django import DjangoScope
from airlock.integrations.executors.celery import celery_executor

with airlock.scope(
    _cls=DjangoScope,           # WHEN: after transaction.on_commit()
    executor=celery_executor,   # HOW: via Celery
    policy=LogOnFlush(logger)   # WHAT: log everything
):
    order.save()
    airlock.enqueue(send_email, order.id)
# Waits for commit, dispatches via Celery, logs
```

```python
# Test scope + sync executor + assertion
with airlock.scope(
    _cls=Scope,                      # WHEN: immediate (no transaction)
    executor=sync_executor,          # HOW: synchronous
    policy=AssertNoEffects()         # WHAT: fail if anything enqueued
):
    test_calculation()
```

```python
# Migration scope + drop all + immediate
with airlock.scope(
    _cls=Scope,                      # WHEN: immediate
    executor=sync_executor,          # HOW: doesn't matter (nothing runs)
    policy=DropAll()                 # WHAT: suppress everything
):
    backfill_data()
```

## Mental Model

Think of airlock as a **buffer with three independent controls**:

```
┌─────────────────────────────────────────┐
│  airlock.enqueue(task, ...)             │ ← Express intent
└──────────────────┬──────────────────────┘
                   │
                   ▼
         ┌─────────────────┐
         │     BUFFER      │ ← Intent stored
         │  [intent list]  │
         └─────────────────┘
                   │
        ┌──────────┼──────────┐
        │          │          │
        ▼          ▼          ▼
    ┌──────┐  ┌──────┐  ┌──────┐
    │POLICY│  │SCOPE │  │EXEC  │ ← 3 independent controls
    │      │  │      │  │      │
    │WHAT? │  │WHEN? │  │HOW?  │
    └──────┘  └──────┘  └──────┘
        │          │          │
        └──────────┼──────────┘
                   │
                   ▼
         task(*args, **kwargs) ← Execution
```

Each concern is **independent**:

- Change WHEN without changing WHAT or HOW
- Change WHAT without changing WHEN or HOW
- Change HOW without changing WHEN or WHAT

This separation enables powerful composition.

## Common Combinations

| Use Case | Scope | Policy | Executor |
|----------|-------|--------|----------|
| **Django production** | `DjangoScope` | `AllowAll` | `celery_executor` |
| **Django test** | `Scope` | `AssertNoEffects` | `sync_executor` |
| **Migration script** | `Scope` | `DropAll` | (doesn't matter) |
| **Admin bulk operation** | `DjangoScope` | `BlockTasks({"send_email"})` | `celery_executor` |
| **Celery task** | `Scope` | `AllowAll` | `celery_executor` |
| **Debug mode** | `Scope` | `LogOnFlush` | `sync_executor` |

## Next

- [How it composes](how-it-composes.md) - Nested scopes and provenance
- [Basic usage guide](../guide/basic-usage.md) - Practical patterns
