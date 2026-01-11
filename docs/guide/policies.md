# Policies Guide

Policies control **what** side effects execute. They filter, observe, and validate intents.

## Built-in Policies

### AllowAll (Default)

```python
with airlock.scope(policy=airlock.AllowAll()):
    airlock.enqueue(anything)  # Always dispatches
```

This is the default - no filtering.

### DropAll

```python
with airlock.scope(policy=airlock.DropAll()):
    airlock.enqueue(send_email)
    airlock.enqueue(charge_card)
    # Nothing dispatches
```

**Use for:**
- Dry-run modes (`--dry-run` flag)
- Testing business logic without side effects
- Suppressing notifications in backfills

### AssertNoEffects

```python
with airlock.scope(policy=airlock.AssertNoEffects()):
    pure_calculation()  # OK
    airlock.enqueue(task)  # Raises PolicyViolation immediately
```

**Use for:**
- Test assertions
- Ensuring code paths are pure
- Catching unexpected side effects

### BlockTasks

Block specific tasks by name:

```python
policy = airlock.BlockTasks({"myapp.tasks:send_email", "myapp.tasks:send_sms"})

with airlock.scope(policy=policy):
    airlock.enqueue(send_email)       # Dropped
    airlock.enqueue(send_sms)          # Dropped
    airlock.enqueue(log_event)         # Dispatches
```

**Fail fast** (raise on enqueue instead of silently dropping):

```python
policy = airlock.BlockTasks({"dangerous_task"}, raise_on_enqueue=True)

with airlock.scope(policy=policy):
    airlock.enqueue(dangerous_task)  # Raises PolicyViolation immediately
```

**Use for:**
- Admin panels (suppress customer notifications)
- Backfills (block emails, allow analytics)
- Feature flags (disable specific tasks)

### LogOnFlush

```python
import logging
logger = logging.getLogger(__name__)

with airlock.scope(policy=airlock.LogOnFlush(logger)):
    airlock.enqueue(task_a)
    airlock.enqueue(task_b)
# Logs each dispatch
```

**Use for:**
- Debugging
- Audit trails
- Observability

### CompositePolicy

Combine multiple policies:

```python
policy = airlock.CompositePolicy(
    airlock.LogOnFlush(logger),
    airlock.BlockTasks({"expensive_task"}),
)

with airlock.scope(policy=policy):
    airlock.enqueue(cheap_task)      # Logged + dispatched
    airlock.enqueue(expensive_task)  # Logged but blocked
```

All policies must allow for the intent to execute.

## Local Policy Contexts

Apply policy to a **region** without creating a new scope:

```python
with airlock.scope():
    airlock.enqueue(task_a)  # Will dispatch

    with airlock.policy(airlock.DropAll()):
        airlock.enqueue(task_b)  # Won't dispatch

    airlock.enqueue(task_c)  # Will dispatch
```

All three intents go to the **same buffer**. Policy is captured per-intent.

## Common Patterns

### Pattern 1: Dry-Run Flag

```python
def backfill_orders(dry_run=False):
    policy = airlock.DropAll() if dry_run else airlock.AllowAll()

    with airlock.scope(policy=policy):
        for order in Order.objects.all():
            order.process()
    # Nothing dispatches if dry_run=True
```

### Pattern 2: Suppress Notifications in Admin

```python
# middleware.py
class AdminAirlockMiddleware(AirlockMiddleware):
    def get_policy(self, request):
        if request.user.is_staff:
            return airlock.BlockTasks({"send_customer_email"})
        return airlock.AllowAll()
```

### Pattern 3: Feature Flags

```python
from django.conf import settings

def get_policy():
    blocked = set()
    if not settings.EMAILS_ENABLED:
        blocked.add("send_email")
    if not settings.SMS_ENABLED:
        blocked.add("send_sms")

    return airlock.BlockTasks(blocked) if blocked else airlock.AllowAll()

with airlock.scope(policy=get_policy()):
    ...
```

### Pattern 4: Environment-Based

```python
if settings.ENV == "development":
    policy = airlock.DropAll()  # No side effects in dev
elif settings.ENV == "staging":
    policy = airlock.BlockTasks({"send_customer_email"})  # No customer emails
else:
    policy = airlock.AllowAll()  # Production
```

### Pattern 5: Conditional Suppression

```python
def process_order(order, suppress_emails=False):
    with airlock.scope():
        order.status = "processed"
        order.save()

        if not suppress_emails:
            airlock.enqueue(send_confirmation, order.id)

        airlock.enqueue(update_analytics, order.id)
```

Or with policy:

```python
def process_order(order, suppress_emails=False):
    policy = airlock.BlockTasks({"send_confirmation"}) if suppress_emails else airlock.AllowAll()

    with airlock.scope(policy=policy):
        order.process()  # Model handles side effects
```

## Policy Behavior

### When Policies Run

**`on_enqueue()`** - Called immediately when `airlock.enqueue()` is invoked:

```python
class LoggingPolicy:
    def on_enqueue(self, intent):
        print(f"Enqueuing: {intent.name}")

with airlock.scope(policy=LoggingPolicy()):
    airlock.enqueue(task)  # Prints "Enqueuing: task"
```

**`allows()`** - Called at flush time for each intent:

```python
class FilterPolicy:
    def allows(self, intent):
        return "safe" in intent.name

with airlock.scope(policy=FilterPolicy()):
    airlock.enqueue(safe_task)    # Allowed
    airlock.enqueue(unsafe_task)  # Dropped
```

### Fail Fast vs Silent Drop

**Fail fast** (raise in `on_enqueue`):

```python
class AssertNoEffects:
    def on_enqueue(self, intent):
        raise PolicyViolation(f"Unexpected effect: {intent.name}")

# Raises immediately at enqueue()
```

**Silent drop** (return False in `allows`):

```python
class DropAll:
    def allows(self, intent):
        return False

# Buffers, then drops at flush
```

**When to use which:**
- Fail fast: Tests, catching bugs
- Silent drop: Production filtering, dry-run modes

