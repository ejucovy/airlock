# The Problem

## Why does airlock exist? What problem does it solve?

Putting side effects deep in the call stack is common but dangerous:

```python
class Order:
    def process(self):
        self.status = "processed"
        notify_warehouse(self.id)
        send_confirmation_email(self.id)
```

It's also tempting to centralize "conditional side effect dispatch" in a deep method. Also dangerous!

```python
class Order:
    def update_status(self, status):
        notify_warehouse(self.id)
        if status == "paid":
            send_confirmation_email(self.id)
        elif status == "shipped":
            update_tracking_system(self.id)
            send_update_email(self.id)
```

But *why* are they dangerous?

- **You can't opt out.** Every scripted creation, fixture load, and migration that calls the method fires the tasks.
- **It's invisible at the call site.** `order.mark_as_paid()` looks innocent. You have to know to trace its call stack for side effects.
- **Testing is miserable.** Mock at the task level (fragile), run a real broker (slow), or `CELERY_ALWAYS_EAGER=True` (hides async bugs).
- **Bulk operations explode.** A loop calling `save()` on 10,000 orders enqueues 10,000 tasks.
- **Re-entrancy bites.** `User.save()` calls `enrich_from_api.delay(user.id)`. That task fetches data, sets `user.age` and `user.income`, then calls `user.save()`... which enqueues `enrich_from_api` again. Now you're adding flags like `_skip_enrich=True` and threading them through everywhere. (Or you're diffing against `Model.objects.get(pk=self.pk)` in every `save()` and using `save(changed_fields=[])` as a task dispatcher. Now you have three problems.)

The problem isn't *where* the intent is expressed. It's that **the effects are silent, and escape immediately**.

## Stuff it all in an airlock

With airlock, you express an _intent_ to perform a side effect, but the side effects don't escape until someone lets them out:

```python
import airlock

class Order:
    def process(self):
        self.status = "processed"
        airlock.enqueue(notify_warehouse, self.id)          # Buffered for later
        airlock.enqueue(send_confirmation_email, self.id)   # Buffered for later
```

Now these methods are a *legitimate* and *safe* place to express domain intent:

- **Colocation.** The model knows when it needs side effects. That knowledge sometimes belongs here.
- **DRY.** Every code path that saves an Order gets the side effects. You can't forget.
- **Control.** The *scope* decides what escapes, not the call site.
- **Visibility.** You can inspect the buffer before it flushes... run a model method and compare before-and-after... great for tests!
- **Control again.** Define your own nested scopes for surgically stacked policies, or even define multiple execution boundaries.

Side effects can be defined close to the source, and still escape in one place.

## What this unlocks

Without airlock, "enqueue side effects at the edge" is an important constraint for maintaining predictable timing, auditability, and control. Side effects deep in the call stack are dangerous, so you're forced to hoist them.

With airlock, both patterns are safe:

- **Edge-only**: All enqueues in views/handlers. Explicit, visible at the boundary.
- **Colocated**: Enqueues near domain logic (`save()`, signals, service methods). DRY, encapsulated.

Choose based on your preferences, not out of necessity.

## Do I really need this...?

- See [Alternatives](alternatives.md)

## Next

- [Core model](core-model.md) - The 3 concerns (Policy/Executor/Scope)
- [How it composes](how-it-composes.md) - Nested scopes and provenance
