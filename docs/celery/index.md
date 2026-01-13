# Celery Integration

Airlock provides first-class integration with Celery, giving you control over when and how tasks are dispatched. You can use Airlock to buffer task dispatch until your code completes successfully, automatically discard tasks when errors occur, and route tasks through Celery's queue system.

There are two main integration points:

1. **Task execution scoping** - Wrap Celery task execution in Airlock scopes so that any side effects enqueued during a task are buffered and only dispatched when the task completes successfully.
2. **Task dispatch via Celery** - Use Celery as the executor so that `airlock.enqueue()` dispatches tasks through Celery's queue system.

These can be used independently or together.

## Installation

```bash
pip install airlock-py celery
```

## Task Execution Scoping

The `@airlock.scoped()` decorator wraps task execution in an Airlock scope. Any side effects enqueued during the task are buffered until the task completes, then dispatched. If the task raises an exception, all buffered effects are discarded.

```python
from celery import Celery
import airlock

app = Celery('myapp')

@app.task
@airlock.scoped()
def process_order(order_id):
    order = fetch_order(order_id)
    order.status = "processed"
    save_order(order)

    # These are buffered within the task's scope
    airlock.enqueue(send_email, order_id=order_id)
    airlock.enqueue(update_analytics, order_id=order_id)
    # Flushes when task completes successfully
    # Discards if task raises exception
```

## Dispatching via Celery

To dispatch tasks through Celery's queue system, use the `celery_executor`. When you pass this executor to a scope, any calls to `airlock.enqueue()` will dispatch via Celery's `.delay()` method when the scope exits.

```python
from airlock.integrations.executors.celery import celery_executor

with airlock.scope(executor=celery_executor):
    airlock.enqueue(send_email, user_id=123)
    airlock.enqueue(process_data, item_id=456)
# Both tasks dispatch via .delay() when scope exits
```

## Combining Both Patterns

You can use task execution scoping and Celery dispatch together. This is a common pattern where tasks are both scoped (so their effects are buffered) and dispatched via Celery:

```python
@app.task
@airlock.scoped()
def process_order(order_id):
    # This task runs in a scope
    order = fetch_order(order_id)
    save_order(order)

    # Dispatch follow-up task via Celery
    airlock.enqueue(send_email, order_id=order_id)

# Trigger it
with airlock.scope(executor=celery_executor):
    airlock.enqueue(process_order, order_id=123)
# process_order.delay(order_id=123) is called
# When it runs, send_email is also queued via Celery
```

## Celery Options

You can pass Celery-specific options like `countdown`, `queue`, and `priority` via the `_dispatch_options` parameter:

```python
airlock.enqueue(
    send_email,
    user_id=123,
    _dispatch_options={
        "countdown": 60,      # Delay 60 seconds
        "queue": "emails",    # Use specific queue
        "priority": 9,        # High priority
    }
)
```

These options are passed through to Celery's `.apply_async()` method.

## Migrating Existing Code

If you have an existing codebase with direct `.delay()` calls, Airlock provides migration tools to help you transition gradually without a big-bang rewrite.

### Selective Migration

For smaller codebases or when you want fine-grained control, apply `LegacyTaskShim` to individual tasks you're migrating:

```python
from airlock.integrations.celery import LegacyTaskShim

@app.task(base=LegacyTaskShim)
def old_task(arg):
    ...

# This now routes through airlock
with airlock.scope():
    old_task.delay(123)  # Emits DeprecationWarning, buffers intent
# Dispatches here
```

**Note:** `LegacyTaskShim` requires an active scope. It will raise `NoScopeError` if called outside a scope.

### Blanket Migration

For large codebases with many `.delay()` calls, you can intercept all tasks globally with a single line of code:

```python
# celery.py
from celery import Celery
from airlock.integrations.celery import install_global_intercept

app = Celery('myapp')

# Patch all tasks globally
install_global_intercept(app)
```

This:
1. Intercepts all `.delay()` and `.apply_async()` calls
2. Routes them through airlock when inside a scope
3. Wraps all task execution in scopes automatically
4. Emits `DeprecationWarning` to encourage migration

Inside scope:
```python
with airlock.scope():
    my_task.delay(123)  # Buffered, returns None
# Dispatches here
```

Outside scope:
```python
my_task.delay(123)  # Passes through to Celery, warns
```

**Note:** Global intercept is a migration tool, not steady-state architecture. Use it to migrate legacy code, but prefer `airlock.enqueue()` for new code.

[Full migration guide](migration.md)

## Using with Django

If you're using Django, the Airlock Django integration provides automatic configuration for Celery. Add Airlock to your `INSTALLED_APPS` and configure it to use the Celery executor:

```python
# settings.py
INSTALLED_APPS = [
    ...
    "airlock.integrations.django",  # Auto-configures airlock
]

MIDDLEWARE = [
    ...
    "airlock.integrations.django.AirlockMiddleware",
]

AIRLOCK = {
    "EXECUTOR": "airlock.integrations.executors.celery.celery_executor",
}
```

With this configuration, every request is automatically scoped, and tasks dispatch via Celery when the request completes successfully:

```python
import airlock

def checkout_view(request):
    order = process_checkout(request)
    airlock.enqueue(send_confirmation, order_id=order.id)
    airlock.enqueue(notify_warehouse, order_id=order.id)
    return HttpResponse("OK")
# Both tasks dispatch via Celery after transaction.on_commit()
```

Celery tasks can also use `@airlock.scoped()` to get the same Django-configured behavior, including transaction-aware dispatch:

```python
@app.task
@airlock.scoped()
def process_order(order_id):
    # Automatically uses DjangoScope with transaction.on_commit()
    order = Order.objects.get(id=order_id)
    airlock.enqueue(send_notification, order_id=order_id)
```

For more details on the Django integration, see the [Django documentation](../django/index.md).
