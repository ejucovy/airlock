# Getting Started

This guide covers airlock basics without framework-specific setup. If you're using Django, see [Django Integration](django/index.md) for a streamlined setup.

## Installation

```bash
pip install airlock-py
```

## Basic Usage

### 1. Enqueue side effects

Use `airlock.enqueue()` to express side effects anywhere in your code:

```python
import airlock

def process_order(order):
    order.status = "processed"
    order.save()
    airlock.enqueue(send_confirmation_email, order.id)
    airlock.enqueue(notify_warehouse, order.id)
```

Side effects don't execute immediately. They're buffered until the surrounding scope decides to dispatch them.

### 2. Wrap execution in a scope

Use `airlock.scope()` to control when effects escape:

```python
import airlock

with airlock.scope():
    process_order(order)
# Side effects dispatch here, after the scope exits
```

If an exception occurs inside the scope, side effects are discarded:

```python
with airlock.scope():
    process_order(order)
    raise ValueError("Something went wrong")
# Side effects are NOT dispatched
```

### 3. Use the decorator for functions

The `@airlock.scoped()` decorator wraps an entire function:

```python
@airlock.scoped()
def handle_checkout(order):
    process_order(order)
    update_inventory(order)
# Side effects dispatch after function returns successfully
```

## Configuring Defaults

Instead of passing arguments to every `scope()` call, configure defaults once at startup:

```python
import airlock
from airlock.integrations.executors.celery import celery_executor

# Set once at app startup
airlock.configure(
    executor=celery_executor,
)

# Now all scopes use Celery by default
with airlock.scope():
    airlock.enqueue(my_task)  # Will dispatch via Celery
```

### Available executors

Airlock provides built-in executors for common task backends:

```python
from airlock.integrations.executors.sync import sync_executor       # Direct function call
from airlock.integrations.executors.celery import celery_executor   # Celery .delay()
from airlock.integrations.executors.django_q import django_q_executor
from airlock.integrations.executors.huey import huey_executor
from airlock.integrations.executors.dramatiq import dramatiq_executor
```

The default executor is `sync_executor`, which calls functions directly.

## Controlling What Executes: Policies

Policies let you filter, observe, or block side effects.

### Drop all effects (dry-run mode)

```python
with airlock.scope(policy=airlock.DropAll()):
    process_order(order)
# Nothing dispatched - useful for dry-runs or migrations
```

### Block specific tasks

```python
with airlock.scope(policy=airlock.BlockTasks({"send_confirmation_email"})):
    process_order(order)
# Warehouse notified, but no confirmation email sent
```

### Assert no effects (for testing)

```python
with airlock.scope(policy=airlock.AssertNoEffects()):
    calculate_total(order)  # Raises if any enqueue() is called
```

### Inspect buffered intents

```python
with airlock.scope(policy=airlock.DropAll()) as scope:
    process_order(order)

    # Inspect what would have been dispatched
    for intent in scope.intents:
        print(f"Task: {intent.name}, Args: {intent.args}")
```

## Putting It Together

Here's a complete example showing configuration and usage:

```python
# app.py
import airlock
from airlock.integrations.executors.celery import celery_executor

# Configure at startup
airlock.configure(executor=celery_executor)

# tasks.py
from celery import shared_task

@shared_task
def send_confirmation_email(order_id):
    ...

@shared_task
def notify_warehouse(order_id):
    ...

# models.py
import airlock
from . import tasks

class Order:
    def process(self):
        self.status = "processed"
        self.save()
        airlock.enqueue(tasks.send_confirmation_email, self.id)
        airlock.enqueue(tasks.notify_warehouse, self.id)

# services.py
import airlock

@airlock.scoped()
def checkout(user, cart):
    order = Order.create(user, cart)
    order.process()
    return order
# Celery tasks dispatch after checkout() returns
```

## Next Steps

- [Core Model](understanding/core-model.md) - Understand the 3 concerns (Scope, Policy, Executor)
- [Testing Guide](testing.md) - Test code that uses airlock
- [Django Integration](django/index.md) - Automatic request-scoped side effects
- [Custom Policies](extending/custom-policies.md) - Write your own filtering logic
- [Custom Executors](extending/custom-executors.md) - Integrate with other task backends
