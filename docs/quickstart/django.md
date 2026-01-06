# Django Quickstart

**Goal:** Get airlock working in Django in 5 minutes with automatic request scoping.

## Install

```bash
pip install airlock
```

## Setup

Add middleware to `settings.py`:

```python
MIDDLEWARE = [
    # ... other middleware ...
    "airlock.integrations.django.AirlockMiddleware",
]
```

Done. Every request now has automatic scoping.

## How It Works

The middleware automatically wraps each request in a scope:

- ✅ Flushes on success (1xx/2xx/3xx responses)
- ❌ Discards on error (4xx/5xx or exception)
- 🔄 Defers to `transaction.on_commit()` automatically

## Basic Usage

In your models/views/services, replace `.delay()` with `airlock.enqueue()`:

```python
import airlock

class Order(models.Model):
    def process(self):
        self.status = "processed"
        self.save()
        airlock.enqueue(send_confirmation_email, order_id=self.id)
        airlock.enqueue(notify_warehouse, order_id=self.id)

# In view
def checkout(request):
    order = Order.objects.get(id=request.POST['order_id'])
    order.process()
    return HttpResponse("OK")
# Side effects dispatch here after response + transaction commit
```

## Configuration

Optional settings:

```python
# settings.py
AIRLOCK = {
    # Use Celery for dispatch
    "TASK_BACKEND": "airlock.integrations.executors.celery.celery_executor",

    # Or use django-q
    # "TASK_BACKEND": "airlock.integrations.executors.django_q.django_q_executor",

    # Defer to transaction.on_commit() (default: True)
    "USE_ON_COMMIT": True,

    # Database for on_commit (default: "default")
    "DATABASE_ALIAS": "default",
}
```

Without `TASK_BACKEND`, tasks run synchronously. Set it to use your queue.

## Management Commands

Wrap commands with `@airlock_command` for automatic scoping:

```python
from django.core.management.base import BaseCommand
from airlock.integrations.django import airlock_command

class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    @airlock_command
    def handle(self, *args, **options):
        # If --dry-run, all side effects dropped automatically
        Order.objects.filter(status='pending').update(status='processed')
```

The decorator:
- Creates scope for command
- Respects `--dry-run` (uses `DropAll()` policy)
- Flushes on success, discards on error

## Manual Scoping

Sometimes you need explicit control outside requests:

```python
from airlock.integrations.django import DjangoScope

# In a Celery task, cron job, etc.
def background_job():
    with airlock.scope(_cls=DjangoScope):
        do_stuff()
    # Effects dispatch after transaction commit
```

## Testing

### Suppress side effects in tests

```python
from django.test import TestCase
import airlock

class OrderTest(TestCase):
    def test_processing_logic(self):
        with airlock.scope(policy=airlock.AssertNoEffects()):
            # Test pure business logic without side effects
            order = Order.objects.create(...)
            order.process()
        # Would raise if any airlock.enqueue() called
```

### Inspect buffered effects

```python
def test_correct_emails_sent(self):
    with airlock.scope() as s:
        order.process()

        # Verify what was enqueued
        assert len(s.intents) == 2
        assert s.intents[0].task.__name__ == "send_confirmation_email"
        assert s.intents[1].task.__name__ == "notify_warehouse"
    # Can verify without actually sending emails
```

## Common Patterns

### Suppress emails in admin

```python
# myapp/middleware.py
from airlock.integrations.django import AirlockMiddleware
import airlock

class AdminAirlockMiddleware(AirlockMiddleware):
    def get_policy(self, request):
        if request.path.startswith('/admin/'):
            return airlock.BlockTasks({"send_confirmation_email"})
        return super().get_policy(request)
```

### Custom flush behavior

```python
class MyAirlockMiddleware(AirlockMiddleware):
    def should_flush(self, request, response):
        # Only flush on 2xx (not 3xx redirects)
        return 200 <= response.status_code < 300
```

## With django-q

Using django-q as your task backend:

```python
# settings.py
AIRLOCK = {
    "TASK_BACKEND": "airlock.integrations.executors.django_q.django_q_executor",
}
```

Now all `airlock.enqueue()` calls dispatch via `async_task()`:

```python
def process_order(order_id):
    # Plain function, no decorator needed
    order = Order.objects.get(id=order_id)
    order.status = "processed"
    order.save()

# In view/command
with transaction.atomic():
    order.save()
    airlock.enqueue(process_order, order_id=order.id)
# Dispatches via async_task() after commit
```

Pass django-q options:

```python
airlock.enqueue(
    heavy_task,
    data=payload,
    _dispatch_options={
        "group": "heavy-jobs",
        "timeout": 300,
        "hook": "my_app.tasks.cleanup_hook"
    }
)
```

## Next Steps

- [Using with Celery](celery.md) - Celery integration
- [Migration guide](../migration/from-direct-delay.md) - Migrate existing code
- [Nested scopes](../guide/nested-scopes.md) - Transaction boundaries
- [Custom policies](../extending/custom-policies.md) - Write your own policies
