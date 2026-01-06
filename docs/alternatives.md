# Alternatives to Airlock

Airlock isn't always the right choice. Here are alternatives and when to use them.

## `transaction.on_commit()`

Django's built-in way to defer execution until transaction commits:

```python
from django.db import transaction

class Order(models.Model):
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        transaction.on_commit(lambda: notify_warehouse.delay(self.id))
```

### When This Works

- You only care about transaction boundaries
- You're okay with limited introspection
- You use `ATOMIC_REQUESTS` consistently

### Limitations

- **Only works in transactions** - If no transaction, runs immediately
- **No opt-out** - Migrations, fixtures trigger callbacks
- **No introspection** - Can't inspect what's queued
- **No policy control** - Can't block specific tasks
- **Confusing with nested transactions** - Savepoints complicate behavior

Airlock gives you `on_commit` behavior (via `DjangoScope`) **plus** policies, introspection, and unified dispatch.

## Django Signals

Signals move **where** code lives, not **when** it executes:

```python
from django.db.models.signals import post_save

@receiver(post_save, sender=Order)
def notify_on_order_save(sender, instance, **kwargs):
    if instance.status == "shipped":
        notify_warehouse.delay(instance.id)
```

### When This Works

- You want to decouple handlers from models
- Multiple independent handlers for same event
- Event-driven architecture

### Limitations

- **Doesn't solve timing** - Tasks still fire immediately
- **Doesn't solve opt-out** - Migrations still trigger signals
- **Implicit coupling** - Hard to find all handlers

Signals are orthogonal to airlock. You can use signals to **trigger** `airlock.enqueue()`.

## Celery Chords/Chains

Define workflow upfront:

```python
from celery import chain, chord

# Sequential
workflow = chain(task_a.s(), task_b.s(), task_c.s())
workflow.apply_async()

# Parallel then collect
callback = collect_results.s()
workflow = chord([task_a.s(), task_b.s(), task_c.s()])(callback)
```

### When This Works

- Workflow is known upfront
- Tasks don't dynamically trigger others
- You want explicit DAG

### Limitations

- **Can't handle dynamic workflows** - Tasks that conditionally trigger others
- **Doesn't help with models** - Still need to decide where to start the chain

Airlock helps when triggers are deep in the call stack, workflow is dynamic/conditional, or you can't hoist to the edge easily.

## Edge-Only Pattern (No Airlock)

Keep all `.delay()` calls in views:

```python
# Model stays pure
class Order(models.Model):
    def mark_shipped(self):
        self.status = "shipped"
        self.save()

# View handles side effects
def ship_order(request, order_id):
    order = Order.objects.get(id=order_id)
    order.mark_shipped()

    notify_warehouse.delay(order.id)
    send_confirmation.delay(order.id)

    return HttpResponse("OK")
```

This is a **valid architecture**. Airlock is for when you want to express intent closer to domain logic.

## When NOT to Use Airlock

Skip airlock if you're happy with edge-only pattern and your team prefers explicit over encapsulated.
