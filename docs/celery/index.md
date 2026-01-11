# Celery Integration

Airlock integrates with Celery to buffer and control task dispatch.

## Quickstart

### Install

```bash
pip install airlock celery
```

### Wrap Task Execution

Use `AirlockTask` as base class to auto-scope task execution:

```python
from celery import Celery
from airlock.integrations.celery import AirlockTask
import airlock

app = Celery('myapp')

@app.task(base=AirlockTask)
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
@app.task(base=AirlockTask)
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

## With Django

Combine Django middleware + Celery executor:

```python
# settings.py
MIDDLEWARE = [
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

## Next Steps

- [Task Wrapper Deep Dive](task-wrapper.md) - Customizing `AirlockTask`
- [Migration Guide](migration.md) - Migrating from direct `.delay()` calls
