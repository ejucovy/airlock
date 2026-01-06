# Nested Scopes

Airlock scopes can be nested. By default, parent scopes **capture** nested scope effects, giving outer scopes authority over what escapes.

## Why Nested Capture?

**Airlock scopes need to compose safely.** Without nested capture, airlock adoption would create an **inverse flywheel** — the more code uses airlock, the less control you have.

### The Problem Without Capture

```python
# Early days: Only your code uses airlock ✓
with TransactionScope():
    order.save()
    charge_payment()  # Plain function, works fine

# Later: A library adopts airlock internally ✗
with TransactionScope():
    order.save()
    payment_lib.process(order)  # Creates nested scope, flushes immediately!
    # Side effects escaped before transaction committed!
```

Without capture, you'd need to **audit every callee** to check if they use airlock. This defeats the abstraction and makes adoption risky.

### The Solution: Capture by Default

```python
# Always safe, regardless of what callees do ✓
with TransactionScope():
    order.save()
    payment_lib.process(order)  # Uses airlock? Captured automatically!
    # All effects held until transaction commits
```

Parent scopes have **authority** over nested scopes. Library code can't bypass your boundaries. Airlock adoption makes your code **more safe**, not less.

## Default Behavior: Capture All

By default, nested scopes are captured by their parent:

```python
with airlock.scope(policy=AllowAll()) as outer:
    airlock.enqueue(task_a)

    with airlock.scope(policy=AllowAll()) as inner:
        airlock.enqueue(task_b)
    # task_b is captured by outer (doesn't dispatch yet)

# Both task_a and task_b dispatch together when outer exits
```

This is the **controlled default** — outer scopes have authority over what escapes.

!!! note "Capture vs Independent Flush"
    Nested scopes are **captured** by default, not flushed independently.
    This ensures compositional safety and is essential for transactional boundaries.
    To allow independent nested scopes, override `before_descendant_flushes()` to return the intents list.

## The `before_descendant_flushes()` Protocol

```python
def before_descendant_flushes(self, exiting_scope: Scope, intents: list[Intent]) -> list[Intent]:
    """
    Called when a nested scope exits and attempts to flush.

    Args:
        exiting_scope: The nested scope that is exiting (may be deeply nested)
        intents: The list of intents the exiting scope wants to flush

    Returns:
        The list of intents to allow through (the nested scope will flush these).
        Any intents not in the returned list are captured into this scope's buffer.

    Default: return [] (capture all intents)
    """
    return []
```

## Provenance Tracking

Parent scopes can distinguish between their own intents and captured intents:

```python
with airlock.scope() as outer:
    airlock.enqueue(task_a)  # outer's own intent

    with airlock.scope() as inner:
        airlock.enqueue(task_b)  # captured from inner

    # Provenance inspection
    assert len(outer.own_intents) == 1      # [task_a]
    assert len(outer.captured_intents) == 1  # [task_b]
    assert len(outer.intents) == 2           # [task_a, task_b]
```

## Use Cases

### 1. Compositional Atomicity

Ensure multi-step operations stay atomic even when steps use nested scopes:

```python
# High-level operation that should be atomic
def checkout_cart(cart_id):
    with airlock.scope():  # Create boundary
        validate_inventory(cart_id)     # May use nested scopes internally
        charge_payment(cart_id)         # May use nested scopes internally
        send_confirmation(cart_id)      # May use nested scopes internally
    # All effects dispatch together — atomic operation ✓

# Call it safely
checkout_cart(123)  # Works correctly regardless of internal implementation
```

### 2. Transactional Boundaries

Ensure all side effects wait for transaction commit:

```python
class TransactionScope(Scope):
    def before_descendant_flushes(self, exiting_scope, intents):
        return []  # Capture all nested effects

with TransactionScope() as txn:
    order.save()
    payment_lib.process(order)  # Uses airlock internally? Captured!
    # Nothing dispatches yet

# All captured tasks dispatch when transaction commits ✓
```

### 3. Timing Control: Batching

Collect effects from nested operations for batch processing:

```python
class EmailBatchingScope(Scope):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.email_batch = []

    def before_descendant_flushes(self, exiting_scope, intents):
        # Capture emails for batching, allow others through
        emails = [i for i in intents if 'email' in i.name]
        non_emails = [i for i in intents if 'email' not in i.name]

        self.email_batch.extend(emails)
        return non_emails  # Non-emails execute immediately

with EmailBatchingScope() as batch:
    process_orders()  # Nested code can enqueue emails
    # Emails collected, other effects dispatched

# Send all emails in one batch
send_batch_emails(batch.email_batch)
```

### 4. Timing Control: Ordering Guarantees

Control execution order across nested operations:

```python
class CacheAfterDBScope(Scope):
    """Ensure DB commits before cache updates"""
    def before_descendant_flushes(self, exiting_scope, intents):
        # Let DB writes through NOW, capture cache updates for LATER
        db_writes = [i for i in intents if 'db' in i.name]
        return db_writes

with CacheAfterDBScope():
    with airlock.scope():
        airlock.enqueue(update_cache, key='foo')  # Captured
        airlock.enqueue(db_commit)                # Dispatches now
    # db_commit has executed ✓

# update_cache executes here, after DB is committed ✓
```

## Creating Independent Nested Scopes

To allow nested scopes to flush independently, override `before_descendant_flushes()`:

```python
class IndependentScope(Scope):
    def before_descendant_flushes(self, exiting_scope, intents):
        return intents  # Allow all intents through

with IndependentScope(policy=AllowAll()) as outer:
    airlock.enqueue(task_a)

    with airlock.scope(policy=AllowAll()) as inner:
        airlock.enqueue(task_b)
    # task_b dispatches here (independent flush)

# Only task_a dispatches here
```

## before_descendant_flushes vs Policy

These control different concerns:

**`Policy`** controls **WHAT** executes (filtering):

```python
# Policy blocks intents entirely
with airlock.scope(policy=BlockTasks({"send_email"})):
    airlock.enqueue(send_email)  # ✗ Blocked - never executes
    airlock.enqueue(log_event)   # ✓ Allowed - executes
```

**`before_descendant_flushes`** controls **WHEN** executes (timing):

```python
# before_descendant_flushes defers intents
class DeferEmailsScope(Scope):
    def before_descendant_flushes(self, exiting_scope, intents):
        # Capture emails for later, allow others now
        return [i for i in intents if 'email' not in i.name]

with DeferEmailsScope():
    with airlock.scope():
        airlock.enqueue(send_email)  # ✓ Captured - executes later
        airlock.enqueue(log_event)   # ✓ Allowed - executes now
    # log_event executed ✓

# send_email executes here ✓ (deferred, not blocked)
```

**Key difference:**
- Policy: Intent **never executes** (filtered out)
- before_descendant_flushes: Intent **executes later** (timing control)

## When to Use Which Extension Point

| Need | Extension Point | What it controls |
|------|----------------|------------------|
| **Filter intents (what)** | `Policy` | What intents are allowed to exist |
| **Change dispatch (how)** | `executor` | How intents execute (Celery, sync, etc.) |
| **Control lifecycle (when)** | `should_flush()` | When scope flushes (success/error) |
| **Control timing (when)** | `before_descendant_flushes()` | When nested intents execute (now/later) |

**Quick decision tree:**

- Block specific tasks entirely? → Use **Policy**
- Change how tasks run (Celery vs sync)? → Use **executor** parameter
- Change when scope flushes (success vs error)? → Override **should_flush()**
- Defer/batch/order nested effects? → Override **before_descendant_flushes()**
