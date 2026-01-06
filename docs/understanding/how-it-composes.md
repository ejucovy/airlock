# How It Composes

Airlock scopes nest safely. Understanding composition is key to using airlock effectively.

## The Composition Problem

Without careful design, nested scopes create an **inverse flywheel**:

```python
# Your code works great ✓
with TransactionScope():
    order.save()
    charge_payment()  # Plain function

# Library adopts airlock... now it breaks ✗
with TransactionScope():
    order.save()
    payment_lib.process(order)  # Creates nested scope!
    # Effects escaped before transaction committed!
```

The more code adopts airlock, the less control you have. That's backwards.

## The Solution: Capture by Default

**Parent scopes have authority over nested scopes.**

```python
with TransactionScope():
    order.save()
    payment_lib.process(order)  # Uses airlock internally? Captured!
    # Effects held until transaction commits ✓
```

Nested scopes **don't flush independently by default**. They're captured by their parent.

## Default Behavior

```python
with airlock.scope() as outer:
    airlock.enqueue(task_a)

    with airlock.scope() as inner:
        airlock.enqueue(task_b)
    # Inner scope exits, but task_b is CAPTURED by outer

# Both task_a and task_b dispatch together here
```

This is the **controlled default**. Library code can't bypass your boundaries.

## Why Capture is Safe

### Compositional Atomicity

Multi-step operations stay atomic even when callees use scopes:

```python
def checkout_cart(cart_id):
    with airlock.scope():
        validate_inventory(cart_id)     # May use scopes internally
        charge_payment(cart_id)         # May use scopes internally
        send_confirmation(cart_id)      # May use scopes internally
    # All effects dispatch atomically ✓

checkout_cart(123)  # Safe regardless of implementation
```

### Transaction Safety

All effects wait for commit:

```python
with transaction.atomic():
    with airlock.scope(_cls=DjangoScope):
        order.save()
        third_party_lib.notify(order)  # Uses airlock? Captured!
    # Nothing dispatches yet
# All effects dispatch after commit ✓
```

## Provenance Tracking

Parent scopes can distinguish their own intents from captured ones:

```python
with airlock.scope() as outer:
    airlock.enqueue(task_a)  # Outer's own intent

    with airlock.scope() as inner:
        airlock.enqueue(task_b)  # Captured from inner

    print(f"Own: {len(outer.own_intents)}")          # 1
    print(f"Captured: {len(outer.captured_intents)}")  # 1
    print(f"Total: {len(outer.intents)}")            # 2
```

This enables:
- Auditing where intents came from
- Different handling for own vs captured
- Debugging nested behavior

## The `before_descendant_flushes` Hook

Advanced: control what happens when nested scopes exit.

```python
class Scope:
    def before_descendant_flushes(
        self,
        exiting_scope: Scope,
        intents: list[Intent]
    ) -> list[Intent]:
        """
        Called when nested scope exits.

        Return intents to allow through.
        Anything not returned is captured.

        Default: return [] (capture all)
        """
        return []
```

### Use Cases

**Selective capture:**

```python
class SafetyScope(Scope):
    """Capture dangerous tasks, allow others through."""

    def before_descendant_flushes(self, exiting_scope, intents):
        safe = [i for i in intents if not i.dispatch_options.get("dangerous")]
        return safe

with SafetyScope():
    with airlock.scope():
        airlock.enqueue(safe_task)              # Allowed through
        airlock.enqueue(
            dangerous_task,
            _dispatch_options={"dangerous": True}
        )                                        # Captured
    # safe_task executed ✓

# dangerous_task executes here ✓
```

**Batching:**

```python
class EmailBatchScope(Scope):
    """Batch emails, allow others through."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.email_batch = []

    def before_descendant_flushes(self, exiting_scope, intents):
        emails = [i for i in intents if 'email' in i.name]
        others = [i for i in intents if 'email' not in i.name]

        self.email_batch.extend(emails)  # Capture for batching
        return others                     # Others execute now

with EmailBatchScope() as batch:
    with airlock.scope():
        airlock.enqueue(send_email, to="user1@example.com")
        airlock.enqueue(log_event, event="email_queued")
    # log_event executes ✓, email captured

# Send batch
send_batch_emails(batch.email_batch)
```

**Independent scopes (opt-out of capture):**

```python
class IndependentScope(Scope):
    """Allow nested scopes to flush independently."""

    def before_descendant_flushes(self, exiting_scope, intents):
        return intents  # Allow all through

with IndependentScope():
    with airlock.scope():
        airlock.enqueue(task)
    # task dispatches here (not captured) ✓
```

## Policy vs Capture

**Policy** controls **WHAT** executes (filtering):

```python
with airlock.scope(policy=BlockTasks({"send_email"})):
    airlock.enqueue(send_email)  # Blocked - never executes
    airlock.enqueue(log_event)   # Allowed - executes
```

**Capture** controls **WHEN** executes (timing):

```python
with airlock.scope() as outer:
    with airlock.scope():
        airlock.enqueue(send_email)  # Captured - executes later
        airlock.enqueue(log_event)   # Captured - executes later
# Both execute here (deferred, not blocked)
```

**Key difference:**
- Policy: intent **filtered out** (never executes)
- Capture: intent **deferred** (executes later at outer scope)

## Extension Points Summary

Control different aspects of composition:

| Extension Point | Controls | Default |
|-----------------|----------|---------|
| **Policy** | What intents are allowed | `AllowAll()` |
| **`should_flush()`** | Whether scope flushes/discards | Flush on success |
| **`before_descendant_flushes()`** | When nested intents execute | Capture all |
| **Executor** | How intents execute | Sync |

These are **independent** and compose freely.

## Mental Model

```
┌─────────────────────────────────────┐
│ Outer Scope                         │
│                                     │
│  Own intent: task_a                 │
│                                     │
│  ┌───────────────────────────────┐ │
│  │ Inner Scope                   │ │
│  │                               │ │
│  │  Own intent: task_b           │ │
│  │                               │ │
│  └───────────────────────────────┘ │
│         │                           │
│         │ before_descendant_flushes()│
│         ▼                           │
│  Captured intent: task_b            │
│                                     │
└─────────────────────────────────────┘
         │
         │ flush()
         ▼
   [task_a, task_b] dispatch together
```

## Common Patterns

### Pattern 1: Transaction Boundary

```python
class TransactionScope(DjangoScope):
    def before_descendant_flushes(self, exiting_scope, intents):
        return []  # Capture all

with transaction.atomic():
    with airlock.scope(_cls=TransactionScope):
        complex_operation()  # May have nested scopes
    # Nothing dispatches yet
# All dispatches after commit ✓
```

### Pattern 2: Conditional Batching

```python
class ConditionalBatchScope(Scope):
    def before_descendant_flushes(self, exiting_scope, intents):
        # Batch high-volume tasks, allow low-volume through
        high_volume = [i for i in intents if i.dispatch_options.get("batch")]
        return [i for i in intents if i not in high_volume]

with ConditionalBatchScope():
    bulk_operation()
    # Low-volume dispatches immediately, high-volume batched
```

### Pattern 3: Ordering Control

```python
class DBBeforeCacheScope(Scope):
    """DB writes now, cache updates later."""

    def before_descendant_flushes(self, exiting_scope, intents):
        db_writes = [i for i in intents if 'db' in i.name]
        return db_writes  # Allow DB writes through now

with DBBeforeCacheScope():
    with airlock.scope():
        airlock.enqueue(update_cache)
        airlock.enqueue(db_write)
    # db_write executes ✓, update_cache captured
# update_cache executes here (after DB commit) ✓
```

## Next

- [Basic usage](../guide/basic-usage.md) - Practical patterns
- [Nested scopes guide](../guide/nested-scopes.md) - Deep dive
- [Custom scopes](../extending/custom-scopes.md) - Subclassing
