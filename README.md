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

```
# settings.py
MIDDLEWARE = [
    # ... other middleware ...
    "airlock.integrations.django.AirlockMiddleware",
]

# models.py
import airlock
import .tasks

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

Read more: [Django integration](docs/django/index.md)

## Installation

```bash
pip install airlock
```

## Documentation

[Full documentation](docs/)

Key pages:

- [The Problem](docs/understanding/the-problem.md) - Why airlock exists
- [Core Model](docs/understanding/core-model.md) - The 3 concerns (Policy/Executor/Scope)
- [Nesting](docs/understanding/nesting.md) - Nested scopes and safety
- [Alternatives](docs/understanding/alternatives.md) - Do I really need this...?

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup.

## License

MIT
