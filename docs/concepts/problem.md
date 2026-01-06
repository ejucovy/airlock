# The Problem

Side effects at a convergent point deep in a call stack -- like model methods -- are dangerous:

```python
class Order:
    def process(self):
        self.status = "processed"
        self.save()
        notify_warehouse.delay(self.id)
        send_confirmation_email(self.id)
```

But *why* are they dangerous?

## The Issues

### No Opt-Out
Every `Order.objects.create()`, fixture load, and migration that touches orders fires the task.

### Invisible at Call Site
`order.status = "shipped"; order.save()` looks innocent. You have to know to check `save()` for side effects.

### Testing is Miserable
Mock at the task level (fragile), run a real broker (slow), or `CELERY_ALWAYS_EAGER=True` (hides async bugs).

### Bulk Operations Explode
A loop calling `save()` on 10,000 orders enqueues 10,000 tasks.

### Re-entrancy Bites
`User.save()` calls `enrich_from_api.delay(user.id)`. That task fetches data, sets `user.age` and `user.income`, then calls `user.save()`... which enqueues `enrich_from_api` again.

Now you're adding flags like `_skip_enrich=True` and threading them through everywhere. (Or you're diffing against `Model.objects.get(pk=self.pk)` in every `save()` and using `save(changed_fields=[])` as a task dispatcher. Now you have three problems.)

## The Root Cause

The problem isn't *where* the intent is expressed. It's that **the effects are silent, and escape immediately**.

## The Solution

With airlock, effects don't escape immediately:

```python
import airlock

class Order:
    def process(self):
        self.status = "processed"
        self.save()
        airlock.enqueue(notify_warehouse, self.id)        # buffered for later
        airlock.enqueue(send_confirmation_email, self.id) # buffered for later
```

Now `save()` is a *legitimate* place to express domain intent:

- **Colocation.** The model knows when it needs side effects. That knowledge sometimes belongs here.
- **DRY.** Every code path that saves an Order gets the side effects. You can't forget.
- **Control.** The *scope* decides what escapes, not the call site.
- **Visibility.** You can inspect the buffer before it flushes, run a model method and compare before-and-after... great for tests!
- **Control again.** Define your own nested scopes for surgically stacked policies, or even define multiple execution boundaries.

Hidden control flow becomes explicit. Side effects can be defined close to the source, and still escape in one place.
