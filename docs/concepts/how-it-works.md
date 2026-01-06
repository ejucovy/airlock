# How It Works

Airlock provides a buffer for side effects and controls when they escape.

## The Pattern

Instead of:

```python
# Direct execution - fires immediately
notify_warehouse.delay(order.id)
```

You write:

```python
# Buffered - fires when scope exits
airlock.enqueue(notify_warehouse, order.id)
```

## Scopes Control Execution

The scope decides **when** and **whether** side effects escape:

```python
# Standard scope: flush on success, discard on error
with airlock.scope():
    order.process()
    # Effects buffered...
# Effects dispatch here (on normal exit)
```

## Policies Control Filtering

Policies decide **what** escapes:

```python
# Drop all side effects
with airlock.scope(policy=airlock.DropAll()):
    order.process()
    # Effects buffered...
# Nothing dispatches (policy blocks everything)
```

## Executors Control How

Executors decide **how** effects execute:

```python
from airlock.integrations.executors.celery import celery_executor

# Use Celery for dispatch
with airlock.scope(executor=celery_executor):
    airlock.enqueue(send_email, user_id=123)
    # Effects buffered...
# Effects dispatched via Celery's .delay()
```

## The Three Concerns

Airlock separates three orthogonal concerns:

| Concern | Controlled By | Question |
|---------|--------------|----------|
| **When** | Scope | When do effects escape? (end of request, after commit, etc.) |
| **What** | Policy | Which effects should execute? (all, none, filtered) |
| **How** | Executor | How should effects run? (sync, Celery, django-q, etc.) |

These can be mixed and matched freely. See [Architecture](../advanced/architecture.md) for details.
