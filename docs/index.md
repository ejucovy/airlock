# Airlock

**Express side effects anywhere. Control whether & when they escape.**

## 30 Second Pitch

Stop worrying about where you call `.delay()`. Write your domain logic naturally, then control side effects at the boundary:

```python
import airlock

class Order:
    def process(self):
        self.status = "processed"
        self.save()
        airlock.enqueue(notify_warehouse, self.id)
        airlock.enqueue(send_confirmation_email, self.id)
```

The **execution context** decides what happens:

```python
# Production: side effects escape
with airlock.scope():
    order.process()

# Migration: suppress everything
with airlock.scope(policy=airlock.DropAll()):
    order.process()

# Test: fail if side effects attempted
with airlock.scope(policy=airlock.AssertNoEffects()):
    test_pure_logic()
```

## Get Started (Choose Your Path)

<div class="grid cards" markdown>

-   :material-language-python:{ .lg .middle } __Raw Python__

    ---

    Just Python, no framework needed

    [:octicons-arrow-right-24: 5 minute quickstart](quickstart/raw-python.md)

-   :simple-django:{ .lg .middle } __Django__

    ---

    Auto-scoping with middleware, transaction-aware

    [:octicons-arrow-right-24: 5 minute quickstart](quickstart/django.md)

-   :material-cog:{ .lg .middle } __Celery__

    ---

    Wrap tasks, migrate `.delay()` calls

    [:octicons-arrow-right-24: 5 minute quickstart](quickstart/celery.md)

</div>

## What Problem Does This Solve?

Side effects in models/services are dangerous:

```python
class Order:
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        send_email.delay(self.id)  # Fires EVERYWHERE
```

- ❌ Migrations trigger emails
- ❌ Tests require mocking
- ❌ Bulk operations explode
- ❌ No control at call site

With airlock, effects are **buffered** and escape **where you decide**:

```python
class Order:
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        airlock.enqueue(send_email, self.id)  # Buffered
```

- ✅ Test scopes suppress effects
- ✅ Migrations use `DropAll()` policy
- ✅ Production flushes at request boundary
- ✅ Full control + visibility

[Understand the problem →](understanding/the-problem.md){ .md-button }

## How It Works (3 Concerns)

Airlock separates three orthogonal concerns:

| Concern | Controlled By | Question |
|---------|---------------|----------|
| **WHEN** | Scope | When do effects escape? (end of request, after commit) |
| **WHAT** | Policy | Which effects execute? (all, none, filtered) |
| **HOW** | Executor | How do they run? (sync, Celery, django-q) |

Mix and match freely:

```python
# Django transaction + Celery dispatch + logging
with airlock.scope(
    _cls=DjangoScope,              # WHEN: after transaction.on_commit()
    executor=celery_executor,      # HOW: via Celery
    policy=LogOnFlush()            # WHAT: log everything
):
    do_stuff()
```

[Learn the core model →](understanding/core-model.md){ .md-button }

## When You DON'T Need This

You're fine without airlock if:

- ✅ All `.delay()` calls are in views (never models/services)
- ✅ Tasks never chain (no task → task)
- ✅ You're happy with constraints above

That's a **valid architecture**. Airlock is for when you want effects closer to domain logic without losing control.

[See alternatives →](alternatives.md)
