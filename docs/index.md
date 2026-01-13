# airlock

**Express side effects anywhere. Control whether & when they escape.**

## tl;dr

```python
import airlock

class Order:
    def process(self):
        self.status = "processed"
        airlock.enqueue(notify_warehouse, self.id)
        airlock.enqueue(send_confirmation_email)
```

The **execution context** decides when (and whether) your side effects actually get dispatched:

```python
# Production API endpoint: flush at end of request
with airlock.scope():
    order.process()
# side effects dispatch here

# Migration: suppress everything
with airlock.scope(policy=airlock.DropAll()):
    order.process()
# nothing dispatched

# Test: fail if anything tries to escape
with airlock.scope(policy=airlock.AssertNoEffects()):
    order.hopefully_pure_function() # raises if any enqueue() called

# Test: surface the side effects
with airlock.scope(policy=airlock.DropAll()) as scope:
    order.process() # raises if any enqueue() called
    assert len(self.intents) == 2
    print((intent.name, intent.args, intent.kwargs) for intent in self.intents)

# Admin API endpoint: selective control
with airlock.scope(policy=airlock.BlockTasks({"send_confirmation_email"})):
    order.process()
    assert len(self.intents) == 2 # the blocked task remains enqueued while we're in the scope
# side effects dispatch or discard here -- warehouse notified, but no confirmation email sent
```

## Using Django? Maybe with Celery?

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

# models.py
import airlock
from . import tasks

class Order(models.Model):
    def process(self):
        self.status = "processed"
        self.save()
        airlock.enqueue(tasks.send_confirmation_email, order_id=self.id)
        airlock.enqueue(tasks.notify_warehouse, order_id=self.id)

# views.py
def checkout(request):
    order = Order.objects.get(id=request.POST['order_id'])
    order.process()
    return HttpResponse("OK")
# Celery tasks dispatch in transaction.on_commit
```

Read more: [Django integration](django/index.md) | [Celery integration](celery/index.md)

## Installation

```bash
pip install airlock-py
```

**Using gevent or eventlet?** Ensure you have `greenlet>=1.0` for correct context isolation. See [Design Invariants](understanding/design-invariants.md#4-concurrent-units-of-work-have-isolated-scopes) for details.

## Documentation

- [The Problem](understanding/the-problem.md) - Why airlock exists
- [Core Model](understanding/core-model.md) - The 3 concerns (Policy/Executor/Scope)
- [Celery](celery/index.md) - Celery integration and migration
- [Extending](extending/custom-policies.md) - Custom policies, executors, and scopes
- [API Reference](api/index.md) - Full API documentation

## Contributing

See [CONTRIBUTING.md](https://github.com/ejucovy/airlock/blob/main/CONTRIBUTING.md) for development setup.

## License

MIT
