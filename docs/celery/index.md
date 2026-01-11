# Celery Integration

Airlock integrates with Celery to buffer and control task dispatch.

## Quickstart

### Install

```bash
pip install airlock celery
```

### Wrap Task Execution

Use `@airlock.scoped()` decorator to auto-scope task execution:

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

### Dispatch via Celery

Use `celery_executor` to dispatch intents through Celery:

```python
from airlock.integrations.executors.celery import celery_executor

with airlock.scope(executor=celery_executor):
    airlock.enqueue(send_email, user_id=123)
    airlock.enqueue(process_data, item_id=456)
# Dispatches via .delay()
```

### Combining Both

Task execution scoping + Celery dispatch:

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

### Pass Celery Options

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

## Migrating Existing Code

### Selective Migration

Apply `LegacyTaskShim` to tasks you're migrating:

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

For large codebases, intercept all tasks globally:

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

⚠️ **Global intercept is a migration tool, not steady state.** Use it to migrate legacy code, but prefer `airlock.enqueue()` for new code.

[Full migration guide →](../migration/from-direct-delay.md)

## With Django

Add to INSTALLED_APPS for automatic configuration:

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

Now every request auto-scopes and dispatches via Celery:

```python
import airlock

def checkout_view(request):
    order = process_checkout(request)
    airlock.enqueue(send_confirmation, order_id=order.id)
    airlock.enqueue(notify_warehouse, order_id=order.id)
    return HttpResponse("OK")
# Both tasks dispatch via Celery after transaction.on_commit()
```

And Celery tasks can use `@airlock.scoped()` to get the same Django-configured behavior:

```python
@app.task
@airlock.scoped()
def process_order(order_id):
    # Automatically uses DjangoScope with transaction.on_commit()
    order = Order.objects.get(id=order_id)
    airlock.enqueue(send_notification, order_id=order_id)
```
