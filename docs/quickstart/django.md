# Django integration

Airlock provides a Django middleware that automatically creates a scopes for your view code. 
Out of the box, Airlock is compatible with many popular task frameworks including Celery, 
django-q, Dramatiq, huey, and Django Tasks.

## How it works

The middleware automatically wraps each request in a scope with the following behaviors:

* All side effects enqueued during a request remain buffered until the end of the request.
* When the Response reaches airlock's middleware:
  * If the response is an error (4xx/5xx or unhandled exception) side effects are discarded.
  * If the response is successful (1xx/2xx/3xx) side effects are dispatched.
    * If you're in a database transaction, side effects will be deferred to `transaction.on_commit()` automatically.

These default behaviors are [configurable](#configuration).

## Installation & setup

```bash
pip install airlock
```

In `settings.py`, add middleware and configure your task framework:

```python
MIDDLEWARE = [
    # ... other middleware ...
    "airlock.integrations.django.AirlockMiddleware",
]

AIRLOCK = {
    "EXECUTOR": "airlock.integrations.executors.celery.celery_executor",
}
```

### Basic usage

Anywhere in your models/views/services/etc, pass your task functions to `airlock.enqueue()`:

```python
## models.py
import airlock
import .tasks

class Order(models.Model):
    def process(self):
        self.status = "processed"
        self.save()
        airlock.enqueue(tasks.send_confirmation_email, order_id=self.id)
        airlock.enqueue(tasks.notify_warehouse, order_id=self.id)

## views.py
def checkout(request):
    order = Order.objects.get(id=request.POST['order_id'])
    order.process()
    return HttpResponse("OK")
# All side effects dispatch here after response + transaction commit
```

### Configuration

With zero configuration, all tasks execute synchronously as plain callables
at dispatch time, hooked in to `transaction.on_commit(robust=True)` against
the default database.

```python
# settings.py
AIRLOCK = {
    # Just call functions synchronously at dispatch time
    "EXECUTOR": "airlock.integrations.executors.sync.sync_executor",
    # Other built in options:
    # "EXECUTOR": "airlock.integrations.executors.celery.celery_executor",
    # "EXECUTOR": "airlock.integrations.executors.django_q.django_q_executor",
    # "EXECUTOR": "airlock.integrations.executors.huey.huey_executor",
    # "EXECUTOR": "airlock.integrations.executors.dramatiq.dramatiq_executor",
    # "EXECUTOR": "airlock.integrations.executors.django_tasks.django_tasks_executor",

    "POLICY": "airlock.AllowAll",
}
```

### Overriding 4xx/5xx behavior

By default airlock's Django middleware discards side effects 
on 4xx/5xx responses and on exceptions. To customize this behavior,
subclass `AirlockMiddleware` and override `should_flush`:

```python
## middleware.py
from airlock.integrations.django import AirlockMiddleware
class UnconditionallyDispatchingAirlockMiddleware(AirlockMiddleware):
    def should_flush(self, request, response):
        return True

## settings.py
MIDDLEWARE = [
    # ...
    "my_app.middleware.UnconditionallyDispatchingAirlockMiddleware",
    # ...
]
```

### Middleware placement

Any placement works for most projects. Django's request handler converts uncaught exceptions to 4xx/5xx responses, so `AirlockMiddleware` typically sees the correct status code and discards appropriately.

Placement matters if you have **custom middleware with `process_exception()`** that catches view exceptions and returns 2xx or 3xx responses. In that case, place `AirlockMiddleware` higher (earlier) in the list than such middleware, so it sees the exception via its own `process_exception` before another middleware converts it to a misleading success response.

If you care about dispatching conditional on exceptions from middleware themselves (not just views), place `AirlockMiddleware` above those middleware. Similarly, if you use `ATOMIC_REQUESTS=False` and maintain your own control over transaction boundaries across middleware layers, you may need to be more opinionated about ordering.

## Airlock in management commands

Wrap commands with `@airlock_command` for automatic scoping:

* All side effects enqueued during a command remain buffered until the end of the command.
* When the command finishes:
  * If there was an unhandled exception, side effects are discarded.
  * If the command is successful, side effects are dispatched.
* If your command supports a `--dry-run` flag, airlock will discard side effects when your command executes in dry-run mode.

```python
from django.core.management.base import BaseCommand
from airlock.integrations.django import airlock_command

class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    @airlock_command
    def handle(self, *args, **options):
        # If --dry-run, all side effects will drop automatically
        # Otherwise, all side effects will dispatch at the end of the script
        for order in Order.objects.filter(status='pending'):
            order.process()
```

## Manual scoping

You can always maintain explicit control too with the context manager API. 
Use `DjangoScope` to pick up settings and transaction-aware dispatch timing:

```python
from airlock.integrations.django import DjangoScope

# In a script, task, etc:
def background_job():
    with airlock.scope(_cls=DjangoScope):
        do_stuff()
    # Effects dispatch after transaction commit

# Or in a view with finer-grained control:
def checkout(request):
    order = Order.objects.get(id=request.POST['order_id'])
    with airlock.scope(_cls=DjangoScope):
        order.process()
    with airlock.scope(_cls=DjangoScope):
        ping_analytics(request.user)
    return HttpResponse("OK")
```

This pattern can also be combined with middleware-based implicit scopes.
You'll want to read more about [how nested scopes work](../guide/nested-scopes.md)
in that case!
