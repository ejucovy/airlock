# When You Don't Need Airlock

You might not need airlock if:

- **Views are the only place you enqueue.** All `.delay()` calls (or `on_commit(lambda: task.delay(...))`) are in views, never in models or reusable services.
- **Tasks don't chain.** No task triggers another task within its code.
- **You use `ATOMIC_REQUESTS`.** Transaction boundaries are already request-scoped, so `on_commit` behaves predictably.
- **You're happy with these constraints.** You accept that domain intent ("notify warehouse when order ships") lives in views, not models.

In this scenario, the view plus the database transaction *is* your boundary.

That's a valid architecture. (I prefer it actually!) Airlock is for when you *want* to express intent closer to the domain -- in `save()`, in signals, in service methods -- without losing control over escape. See [What This Unlocks](../index.md#what-this-unlocks) for how airlock makes this a choice rather than a constraint.
