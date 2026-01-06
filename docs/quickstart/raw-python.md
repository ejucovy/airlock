# Raw Python Quickstart

**Goal:** Get airlock working in 5 minutes without any framework.

## Install

```bash
pip install airlock
```

## Basic Pattern

```python
import airlock

# 1. Use airlock.enqueue() instead of direct calls
def process_order(order_id):
    order = fetch_order(order_id)
    order.status = "processed"
    save_order(order)

    airlock.enqueue(send_email, order_id=order_id)
    airlock.enqueue(notify_warehouse, order_id=order_id)

# 2. Wrap execution in a scope
with airlock.scope():
    process_order(123)
# Side effects dispatch here when scope exits
```

That's it. Effects buffer during execution, dispatch at scope exit.

## Controlling Behavior

### Drop everything (dry-run mode)

```python
with airlock.scope(policy=airlock.DropAll()):
    process_order(123)
# Nothing dispatches
```

### Assert no side effects (testing)

```python
def test_pure_calculation():
    with airlock.scope(policy=airlock.AssertNoEffects()):
        result = calculate_total(cart)  # OK
        airlock.enqueue(send_email)     # Raises PolicyViolation
```

### Block specific tasks

```python
with airlock.scope(policy=airlock.BlockTasks({"send_email"})):
    process_order(123)
# notify_warehouse dispatches, send_email doesn't
```

### Inspect before dispatch

```python
with airlock.scope() as s:
    process_order(123)

    # Check what's buffered
    print(f"Buffered {len(s.intents)} side effects:")
    for intent in s.intents:
        print(f"  - {intent.name}")
# Dispatches here
```

## Using Task Queues

### With Celery

```python
from airlock.integrations.executors.celery import celery_executor

with airlock.scope(executor=celery_executor):
    airlock.enqueue(celery_task, arg=123)
# Dispatches via celery_task.delay(arg=123)
```

### With django-q

```python
from airlock.integrations.executors.django_q import django_q_executor

with airlock.scope(executor=django_q_executor):
    airlock.enqueue(any_function, arg=123)
# Dispatches via async_task(any_function, arg=123)
```

## Common Patterns

### Local policy override

```python
with airlock.scope():
    airlock.enqueue(task_a)  # Will dispatch

    with airlock.policy(airlock.DropAll()):
        airlock.enqueue(task_b)  # Won't dispatch

    airlock.enqueue(task_c)  # Will dispatch
# task_a and task_c dispatch, task_b dropped
```

### Pass dispatch options

```python
airlock.enqueue(
    send_email,
    user_id=123,
    _dispatch_options={"countdown": 60, "queue": "emails"}
)
# Options passed to underlying queue (Celery, etc)
```

## Next Steps

- [Understand the problem](../understanding/the-problem.md) - Why airlock exists
- [Policies guide](../guide/policies.md) - Built-in and custom policies
- [Nested scopes](../guide/nested-scopes.md) - Composition and capture
- [Celery integration](celery.md) - Wrap Celery tasks
