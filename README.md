# airlock

**Express side effects anywhere. Control whether & when they escape.**

[![Tests](https://github.com/ejucovy/airlock/actions/workflows/tests.yml/badge.svg)](https://github.com/ejucovy/airlock/actions/workflows/tests.yml)
[![Docs](https://github.com/ejucovy/airlock/actions/workflows/docs.yml/badge.svg)](https://ejucovy.github.io/airlock)
[![codecov](https://codecov.io/gh/ejucovy/airlock/graph/badge.svg?token=AZ8U5BHG1M)](https://codecov.io/gh/ejucovy/airlock)

<img width="1263" height="550" alt="Airlock diagram" src="https://github.com/user-attachments/assets/d5aa2526-53d4-40a7-a6de-8589a5e7cad6" style="max-width: 100%; height: auto;" />

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
    order.process()
    assert len(scope.intents) == 2
    print((intent.name, intent.args, intent.kwargs) for intent in scope.intents)

# Admin API endpoint: selective control
with airlock.scope(policy=airlock.BlockTasks({"send_confirmation_email"})) as scope:
    order.process()
    assert len(scope.intents) == 2  # the blocked task remains enqueued while we're in the scope
# side effects dispatch or discard here -- warehouse notified, but no confirmation email sent 
```

## Using Django? Maybe with Celery?

```
# settings.py
MIDDLEWARE = [
    # ... other middleware ...
    "airlock.integrations.django.AirlockMiddleware",
]

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
# Celery tasks dispatch in middleware, after transaction has committed
```

Read more: [Django integration](https://ejucovy.github.io/airlock/django/)

## Installation

```bash
pip install airlock-py
```

## Documentation

[Full documentation](https://ejucovy.github.io/airlock/)

Key pages:

- [The Problem](https://ejucovy.github.io/airlock/understanding/the-problem/) - Why airlock exists
- [Core Model](https://ejucovy.github.io/airlock/understanding/core-model/) - The 3 concerns (Policy/Executor/Scope)
- [Nesting](https://ejucovy.github.io/airlock/understanding/nesting/) - Nested scopes and safety
- [Alternatives](https://ejucovy.github.io/airlock/understanding/alternatives/) - Do I really need this...?

## Contributing

See [CONTRIBUTING.md](https://github.com/ejucovy/airlock/blob/main/CONTRIBUTING.md) for development setup.

## License

MIT
