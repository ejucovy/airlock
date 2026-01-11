# Selective vs Blanket Migration

Choosing the right migration strategy for your codebase.

## Decision Tree

```
Do you have 100+ .delay() calls?
├─ Yes → Start with blanket migration
└─ No  → Use selective migration

Is this a new feature/module?
├─ Yes → Use greenfield (airlock.enqueue from start)
└─ No  → Continue below

Can you afford 1-2 weeks of migration work?
├─ Yes → Selective migration (safest)
└─ No  → Blanket migration (fastest)
```

## Selective Migration

### How It Works

Apply `LegacyTaskShim` to individual tasks:

```python
from airlock.integrations.celery import LegacyTaskShim

@app.task(base=LegacyTaskShim)
def notify_warehouse(order_id):
    ...
```

Migrate one task at a time, replacing `.delay()` calls at your own pace.

### Pros

- ✅ **Safe** - Explicit about what's migrated
- ✅ **Controlled** - Migrate critical paths first
- ✅ **Clear** - Easy to see migration progress
- ✅ **Testable** - Test each task individually

### Cons

- ❌ **Slow** - Must apply shim to each task
- ❌ **Requires scopes** - Raises `NoScopeError` outside scopes
- ❌ **Incomplete coverage** - Un-shimmed tasks still use old behavior

### When to Use

- You have < 50 tasks
- You want explicit control
- You can afford time to migrate properly
- You're risk-averse

### Migration Steps

1. **Identify critical tasks** - Start with high-value paths
2. **Add shim to one task**
3. **Add scopes to call sites** - Ensure no `NoScopeError`
4. **Test thoroughly**
5. **Replace `.delay()` with `airlock.enqueue()`** (optional)
6. **Repeat for next task**

## Blanket Migration

### How It Works

Intercept ALL tasks globally:

```python
# celery.py
from airlock.integrations.celery import install_global_intercept

app = Celery('myapp')
install_global_intercept(app)
```

Every task is automatically intercepted and wrapped.

### Pros

- ✅ **Fast** - One line of code
- ✅ **Complete** - Covers all tasks immediately
- ✅ **Graceful** - Works outside scopes (warns, doesn't break)
- ✅ **Auto-wraps execution** - Tasks run in scopes automatically

### Cons

- ❌ **Global side effects** - Monkey-patches Celery
- ❌ **Migration tool** - Not intended for steady-state
- ❌ **Less control** - Everything migrated at once
- ❌ **Returns None** - `.delay()` returns `None` inside scopes

### When to Use

- You have 100+ tasks
- You need quick proof-of-concept
- You're refactoring a legacy codebase
- You want immediate benefits with gradual cleanup

### Migration Steps

1. **Install global intercept** - One line in `celery.py`
2. **Test critical paths** - Ensure scopes exist where needed
3. **Monitor warnings** - Find `.delay()` calls to replace
4. **Gradually replace** - `task.delay()` → `airlock.enqueue(task)`
5. **Remove intercept** - When all `.delay()` replaced

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

## Gotchas

### Blanket + AirlockTask = Double Scopes

Don't use both:

```python
# ❌ Bad - creates nested scopes
install_global_intercept(app)  # Wraps execution in scope

@app.task(base=AirlockTask)  # Also wraps execution in scope
def my_task():
    ...
```

Choose one:
- Blanket intercept with `wrap_task_execution=True` (default)
- OR explicit `AirlockTask` base class

### Selective Requires Scopes Everywhere

```python
@app.task(base=LegacyTaskShim)
def shimmed_task():
    ...

# ❌ Fails - no scope
shimmed_task.delay()

# ✅ Works - has scope
with airlock.scope():
    shimmed_task.delay()
```

Blanket migration allows outside scopes (warns, doesn't break).

## Recommendation

**For most teams:** Start with blanket migration, gradually replace `.delay()` calls.

**For small teams/codebases:** Use selective migration for explicit control.

**For new code:** Skip migration entirely, use `airlock.enqueue()` from day 1.

