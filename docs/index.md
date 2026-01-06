# Airlock

**Express side effects anywhere. Control whether & when they escape.**

## The Idea

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
# HTTP endpoint: flush at end of request
with airlock.scope():
    order.process()
# side effects dispatch here

# Migration script: suppress everything
with airlock.scope(policy=airlock.DropAll()):
    order.process()
# nothing dispatched

# Test: fail if anything tries to escape
with airlock.scope(policy=airlock.AssertNoEffects()):
    test_pure_logic()
# raises if any enqueue() called

# Admin-facing HTTP endpoint: flush at end of request with selective filtering
with airlock.scope(policy=airlock.BlockTasks({"send_confirmation_email"})):
    order.process()
# warehouse gets notified, customer doesn't get emailed
```

!!! note "Django Integration"
    If you're using Django, you can ignore `with airlock.scope()` -- it'll hook in where you expect. More on this in the [Django integration guide](integrations/django.md).

## What This Unlocks

Without airlock, "enqueue side effects at the edge" is an important constraint for maintaining predictable timing, auditability, and control. Side effects deep in the call stack are dangerous, so you're forced to hoist them.

With airlock, both patterns are safe:

- **Edge-only**: All enqueues in views/handlers. Explicit, visible at the boundary.
- **Colocated**: Enqueues near domain logic (`save()`, signals, service methods). DRY, encapsulated.

Choose based on your team's preferences, not out of necessity. See [When You Don't Need This](getting-started/when-not-needed.md) for more on picking your style.

## Integration-Aware Default Boundaries

When you use the Django and Celery integrations, effects escape by default where you would expect:

| Context | When | Dispatch if | Discard if |
|---------|------|-------------|------------|
| **HTTP request** | End of request, deferred to `on_commit` | 1xx/2xx/3xx response | 4xx/5xx or exception |
| **Management command** | End of `handle()` | Normal exit | Exception (or `--dry-run`) |
| **Celery task** | End of task | Success | Exception |

Each integration provides sensible defaults. Override with policies or custom scope classes. Or use the lower-level `with airlock.scope()` API to control behaviors explicitly in your own code.

## Quick Links

- [Installation](getting-started/installation.md) - Get started in minutes
- [Quick Start](getting-started/quick-start.md) - Basic usage examples
- [Core Concepts](concepts/problem.md) - Understand the problem airlock solves
- [Integrations](integrations/django.md) - Django, Celery, and more
- [API Reference](api/context-manager.md) - Complete API documentation
