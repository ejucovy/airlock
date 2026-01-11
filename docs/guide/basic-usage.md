# Basic Usage

Core patterns for everyday use.

## The Basic Pattern

```python
import airlock

# 1. Express intent with airlock.enqueue()
def process_order(order_id):
    order = get_order(order_id)
    order.status = "processed"
    save(order)

    airlock.enqueue(notify_warehouse, order_id=order_id)
    airlock.enqueue(send_confirmation, order_id=order_id)

# 2. Wrap in a scope
with airlock.scope():
    process_order(123)
# Effects dispatch here
```

## Scope Lifecycle

**On normal exit:** calls `flush()` - intents dispatch

**On exception:** calls `discard()` - intents dropped

```python
with airlock.scope():
    airlock.enqueue(task_a)
    raise Exception()  # Scope discards, task_a doesn't run
```

## Local Policy Context

Apply policy to a region without creating a new scope:

```python
with airlock.scope():
    airlock.enqueue(task_a)  # Will dispatch

    with airlock.policy(airlock.DropAll()):
        airlock.enqueue(task_b)  # Won't dispatch

    airlock.enqueue(task_c)  # Will dispatch
```

All three intents go to the same buffer. Policy is captured per-intent.

## Inspecting the Buffer

```python
with airlock.scope() as s:
    do_stuff()

    # Check what's buffered
    for intent in s.intents:
        print(f"{intent.name}: {intent.args}, {intent.kwargs}")
```

## Pass Dispatch Options

```python
airlock.enqueue(
    send_email,
    user_id=123,
    _dispatch_options={"countdown": 60, "queue": "emails"}
)
```

Options are executor-specific (Celery, django-q, etc.)

## Get Current Scope

```python
scope = airlock.get_current_scope()
if scope:
    print(f"In scope with {len(scope.intents)} intents buffered")
```

## Error Handling

**No scope:**

```python
airlock.enqueue(task)  # Raises NoScopeError
```

This is intentional - side effects require explicit boundaries.

**Policy violation:**

```python
with airlock.scope(policy=airlock.AssertNoEffects()):
    airlock.enqueue(task)  # Raises PolicyViolation immediately
```

