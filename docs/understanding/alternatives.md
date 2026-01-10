# Alternatives

## `transaction.on_commit()`

In many Django projects, the typical pattern evolution is to start with immediately-escaping tasks:

```python
class Order:
    def process(self):
        self.status = "processed"
        self.save()
        notify_warehouse.delay(self.id)
        send_confirmation_email(self.id)
```

And then migrate to a transaction boundary:

```python
class Order:
    def process(self):
        self.status = "processed"
        self.save()
        transaction.on_commit(lambda: notify_warehouse.delay(self.id))
        transaction.on_commit(lambda: send_confirmation_email(self.id))
```

This solves one problem: don't fire if the transaction rolls back, and don't fire until database state has settled. But it doesn't solve the rest:

- **Only works inside a transaction.** If you call `on_commit()` while there isn't an open transaction, the callback will be executed immediately. So the temporal sequence of your code changes silently based on both global configuration (`ATOMIC_REQUESTS`) and any given call stack (`with transaction.atomic()`) -- yikes!
- **No opt-out.** Migrations, fixtures, tests still trigger.
- **No introspection.** Can't ask "what's about to fire?"
- **No policy control.** Can't suppress specific tasks or block regions.
- **What about sequential transactions? What about savepoints (nested transactions)?** Hard to reason about! (Your side effects will run after each outermost transaction commits, in the order they were registered within that transaction's scope.)

Airlock gives you `on_commit` behavior (via `DjangoScope`) *plus* policies, introspection, and a single dispatch boundary.

## Django signals

Signals move *where* the side effect lives, not *whether* or *when* it fires. This is a powerful tool for code organization, but it doesn't address the core problems.

## Celery chords/chains

If your tasks trigger other tasks, consider whether the workflow should be defined upfront instead. `chain(task_a.s(), task_b.s())` makes the cascade explicit with no hidden enqueues.

Airlock helps when that's not practical: triggers deep in the call stack that can't be extracted trivially; tasks that conditionally trigger others; or when you legitimately want to keep your side effect intents DRY across all callers.

## When you don't need this

You might not need airlock if:

- **Views are the only place you enqueue.** All `.delay()` calls are in views, never in models or reusable services.
- **Tasks don't chain internally.** No task triggers another task within its code.
- **You use `ATOMIC_REQUESTS`.** Transaction boundaries are already request-scoped, so `on_commit` behaves predictably.
- **You always remember to hook into `transaction.on_commit`**. All your view code reliably runs `transaction.on_commit(functools.partial(task.delay, ...))` so side effects never escape out of an incomplete or rolled-back transaction.
- **You're happy with these constraints.** You accept that domain intent ("notify warehouse when order ships") lives in views, not models.

In this scenario, the view plus the database transaction *is* your boundary.

That's a valid architecture. (I prefer it actually!) Airlock is for when you *want* to express intent closer to the domain -- in `save()`, in signals, in service methods -- without losing control over escape.

## Next

- [Core model](core-model.md) - The 3 concerns (Policy/Executor/Scope)
- [How it composes](how-it-composes.md) - Nested scopes and provenance
