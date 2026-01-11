# Migration Guide

How to migrate an existing codebase from direct Celery `.delay()` calls to airlock.

## The Challenge

You have code like this scattered everywhere:

```python
class Order(models.Model):
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        notify_warehouse.delay(self.id)
        send_email.delay(self.id)

# And in views
def process_order(request, order_id):
    order.process()
    analytics.delay(order.id)
    return HttpResponse("OK")
```

Changing every `.delay()` to `airlock.enqueue()` is tedious and error-prone.

## Decision Tree

```
Do you have 100+ .delay() calls?
+-- Yes -> Start with blanket migration
+-- No  -> Use selective migration

Is this a new feature/module?
+-- Yes -> Use greenfield (airlock.enqueue from start)
+-- No  -> Continue below

Can you afford 1-2 weeks of migration work?
+-- Yes -> Selective migration (safest)
+-- No  -> Blanket migration (fastest)
```

## Strategy 1: Selective Migration (Recommended)

Migrate tasks one at a time using `LegacyTaskShim`:

```python
from airlock.integrations.celery import LegacyTaskShim

# Apply to tasks you're migrating
@app.task(base=LegacyTaskShim)
def notify_warehouse(order_id):
    ...

# Old code still works (inside scopes)
with airlock.scope():
    notify_warehouse.delay(order_id)  # Routes through airlock, warns
```

**Behavior:**
- Inside scope: routes through airlock, returns `None`
- Outside scope: raises `NoScopeError`
- Always emits `DeprecationWarning`

**Migration path:**
1. Add `LegacyTaskShim` to one task
2. Ensure all call sites have scopes
3. Replace `.delay()` with `airlock.enqueue()` at your leisure
4. Remove `LegacyTaskShim` when done

### Pros

- **Safe** - Explicit about what's migrated
- **Controlled** - Migrate critical paths first
- **Clear** - Easy to see migration progress
- **Testable** - Test each task individually

### Cons

- **Slow** - Must apply shim to each task
- **Requires scopes** - Raises `NoScopeError` outside scopes
- **Incomplete coverage** - Un-shimmed tasks still use old behavior

## Strategy 2: Blanket Migration

Intercept ALL tasks globally:

```python
# celery.py
from celery import Celery
from airlock.integrations.celery import install_global_intercept

app = Celery('myapp')

# Patch all tasks at startup
install_global_intercept(app)
```

**Behavior:**
- Inside scope: routes through airlock, returns `None`
- Outside scope: passes through to Celery, warns
- Always emits `DeprecationWarning`
- Wraps all task execution in scopes automatically

**Use for:**
- Large codebases with 100s of `.delay()` calls
- Quick proof-of-concept
- Gradual migration without breaking existing code

!!! warning
    This is a **migration tool**, not steady-state architecture. It monkey-patches Celery globally. Plan to replace `.delay()` with `airlock.enqueue()` over time.

### Pros

- **Fast** - One line of code
- **Complete** - Covers all tasks immediately
- **Graceful** - Works outside scopes (warns, doesn't break)
- **Auto-wraps execution** - Tasks run in scopes automatically

### Cons

- **Global side effects** - Monkey-patches Celery
- **Migration tool** - Not intended for steady-state
- **Less control** - Everything migrated at once
- **Returns None** - `.delay()` returns `None` inside scopes

## Strategy 3: Greenfield (New Code)

Just use `airlock.enqueue()` from the start:

```python
import airlock

class Order(models.Model):
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        airlock.enqueue(notify_warehouse, self.id)

# In views (with Django middleware)
def process_order(request, order_id):
    order.process()  # Effects auto-scoped by middleware
    return HttpResponse("OK")
```

No shims, no warnings, no migration needed.

## Comparison

| Approach | Effort | Risk | Use When |
|----------|--------|------|----------|
| **Selective** | Medium | Low | Methodical migration, want control |
| **Blanket** | Low | Medium | Large codebase, need quick win |
| **Greenfield** | Low | None | New project or isolated feature |

## Hybrid Approach

Use both strategies:

```python
# celery.py - Global intercept for most tasks
install_global_intercept(app, wrap_task_execution=False)

# Critical tasks - Explicit shimming for control
@app.task(base=LegacyTaskShim)
def critical_payment_task(order_id):
    ...
```

This gives:
- Blanket coverage for routine tasks
- Explicit control for critical tasks
- Gradual migration path

## Common Patterns

### Pattern 1: Start Blanket, Finish Selective

```python
# Week 1: Install blanket migration
install_global_intercept(app)

# Week 2-4: Add scopes to critical paths
with airlock.scope():
    process_order()

# Week 5+: Replace .delay() with airlock.enqueue()
# Old: task.delay(arg)
# New: airlock.enqueue(task, arg)

# Eventually: Remove intercept when all replaced
```

### Pattern 2: Selective for New, Blanket for Old

```python
# New feature: Use airlock.enqueue from start
def new_checkout_flow():
    airlock.enqueue(new_task, ...)

# Legacy code: Blanket intercept
install_global_intercept(app)
```

### Pattern 3: Feature Flag Migration

```python
# settings.py
USE_AIRLOCK = env.bool("USE_AIRLOCK", default=False)

# celery.py
if settings.USE_AIRLOCK:
    install_global_intercept(app)
```

Test in staging, roll out gradually.

## Common Issues

### Issue: `NoScopeError` with `LegacyTaskShim`

```python
notify_warehouse.delay(123)  # NoScopeError!
```

**Fix:** `LegacyTaskShim` requires a scope. Add one:

```python
with airlock.scope():
    notify_warehouse.delay(123)  # Works
```

Or use `install_global_intercept()` instead (allows outside scopes).

### Issue: Return value is `None`

```python
result = task.delay(123)
result.get()  # AttributeError: 'NoneType' has no attribute 'get'
```

**Why:** Inside scopes, `.delay()` returns `None` because dispatch is deferred.

**Fix:** Stop relying on `AsyncResult`. Decouple intent from result tracking. If you need results, use a different pattern (callbacks, database polling, etc.).

### Issue: Warnings everywhere

```python
DeprecationWarning: task.delay() is deprecated, use airlock.enqueue()
```

**Fix:** This is intentional! Replace `.delay()` with `airlock.enqueue()`:

```python
# Old
task.delay(arg)

# New
airlock.enqueue(task, arg)
```

### Issue: Blanket + AirlockTask = Double Scopes

Don't use both:

```python
# Bad - creates nested scopes
install_global_intercept(app)  # Wraps execution in scope

@app.task(base=AirlockTask)  # Also wraps execution in scope
def my_task():
    ...
```

Choose one:
- Blanket intercept with `wrap_task_execution=True` (default)
- OR explicit `AirlockTask` base class

## Recommendation

**For most teams:** Start with blanket migration, gradually replace `.delay()` calls.

**For small teams/codebases:** Use selective migration for explicit control.

**For new code:** Skip migration entirely, use `airlock.enqueue()` from day 1.
