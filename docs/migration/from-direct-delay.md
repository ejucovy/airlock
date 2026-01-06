# Migrating from Direct .delay() Calls

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
- ✅ Inside scope: routes through airlock, returns `None`
- ❌ Outside scope: raises `NoScopeError`
- ⚠️ Always emits `DeprecationWarning`

**Migration path:**
1. Add `LegacyTaskShim` to one task
2. Ensure all call sites have scopes
3. Replace `.delay()` with `airlock.enqueue()` at your leisure
4. Remove `LegacyTaskShim` when done

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
- ✅ Inside scope: routes through airlock, returns `None`
- ✅ Outside scope: passes through to Celery, warns
- ⚠️ Always emits `DeprecationWarning`
- 🔄 Wraps all task execution in scopes automatically

**Use for:**
- Large codebases with 100s of `.delay()` calls
- Quick proof-of-concept
- Gradual migration without breaking existing code

**⚠️ Warning:** This is a **migration tool**, not steady-state architecture. It monkey-patches Celery globally. Plan to replace `.delay()` with `airlock.enqueue()` over time.

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

## Next Steps

- [Selective vs Blanket](selective-vs-blanket.md) - Choosing migration strategy
- [Celery Task Wrapper](../integrations/celery/task-wrapper.md) - `AirlockTask` deep dive
