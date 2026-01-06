# airlock

**Express side effects anywhere. Control whether & when they escape.**

```python
import airlock

class Order:
    def process(self):
        self.status = "processed"
        self.save()
        airlock.enqueue(notify_warehouse, self.id)
        airlock.enqueue(send_confirmation_email, self.id)
```

The **execution context** decides when (and whether) your side effects actually get dispatched:

```python
# Production: flush at end of request
with airlock.scope():
    order.process()
# side effects dispatch here

# Migration: suppress everything
with airlock.scope(policy=airlock.DropAll()):
    order.process()
# nothing dispatched

# Test: fail if anything tries to escape
with airlock.scope(policy=airlock.AssertNoEffects()):
    test_pure_logic()
# raises if any enqueue() called
```

## Installation

```bash
pip install airlock
```

## Quick Start

Choose your path:

- **[Raw Python (5 min)](docs/quickstart/raw-python.md)** - Just Python, no framework needed
- **[Django (5 min)](docs/quickstart/django.md)** - Auto-scoping with middleware
- **[Celery (5 min)](docs/quickstart/celery.md)** - Wrap tasks, migrate `.delay()` calls

## Documentation

**[Full documentation →](docs/)**

Key pages:

- [The Problem](docs/understanding/the-problem.md) - Why airlock exists
- [Core Model](docs/understanding/core-model.md) - The 3 concerns (Policy/Executor/Scope)
- [How It Composes](docs/understanding/how-it-composes.md) - Nested scopes and safety

## The Problem

Side effects deep in the call stack are dangerous:

```python
class Order(models.Model):
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        notify_warehouse.delay(self.id)  # Fires EVERYWHERE
```

- ❌ Migrations trigger emails
- ❌ Tests require mocking
- ❌ Bulk operations explode
- ❌ No control at call site

## The Solution

With airlock, effects are **buffered** and escape **where you decide**:

```python
import airlock

class Order(models.Model):
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        airlock.enqueue(notify_warehouse, self.id)  # Buffered

# Production
with airlock.scope():
    order.save()  # Effects dispatch here

# Migration
with airlock.scope(policy=airlock.DropAll()):
    order.save()  # Nothing dispatches

# Test
with airlock.scope(policy=airlock.AssertNoEffects()):
    order.save()  # Raises if any side effects
```

## Core Concepts

Airlock separates three orthogonal concerns:

| Concern | Controlled By | Question |
|---------|---------------|----------|
| **WHEN** | Scope | When do effects escape? |
| **WHAT** | Policy | Which effects execute? |
| **HOW** | Executor | How do they run? |

Mix and match freely:

```python
# Django transaction + Celery dispatch + logging
with airlock.scope(
    _cls=DjangoScope,           # WHEN: after transaction.on_commit()
    executor=celery_executor,   # HOW: via Celery
    policy=LogOnFlush()         # WHAT: log everything
):
    do_stuff()
```

## When You Don't Need This

You might not need airlock if:

- ✅ All `.delay()` calls are in views (never models/services)
- ✅ Tasks never chain
- ✅ You're happy with these constraints

That's a **valid architecture**. Airlock is for when you want effects closer to domain logic without losing control.

[See alternatives →](docs/alternatives.md)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup.

## License

MIT
