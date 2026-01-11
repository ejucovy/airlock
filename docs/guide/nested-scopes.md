# Nested Scopes Guide

Practical patterns for composing scopes safely.

## The Default: Capture

Nested scopes are **captured** by default:

```python
with airlock.scope() as outer:
    airlock.enqueue(task_a)

    with airlock.scope() as inner:
        airlock.enqueue(task_b)
    # task_b captured by outer (doesn't dispatch)

# Both task_a and task_b dispatch together
```

This is **compositional safety** - parent scopes have authority over nested scopes.

## Why Capture Matters

Without capture, library code could bypass your boundaries:

```python
# Your code
with TransactionScope():
    order.save()
    payment_lib.process(order)  # Uses airlock internally
    # If nested scope flushed independently, effects escaped before commit!
```

With capture:

```python
# Your code
with TransactionScope():
    order.save()
    payment_lib.process(order)  # Nested scope captured
    # Nothing dispatches yet
# All effects dispatch after commit ✓
```

## Provenance Tracking

Distinguish your intents from captured intents:

```python
with airlock.scope() as outer:
    airlock.enqueue(task_a)  # Own intent

    with airlock.scope():
        airlock.enqueue(task_b)  # Captured intent

    print(f"Own: {len(outer.own_intents)}")          # 1
    print(f"Captured: {len(outer.captured_intents)}")  # 1
    print(f"Total: {len(outer.intents)}")            # 2
```

**Use for:**
- Debugging ("where did this come from?")
- Metrics ("how many intents from nested scopes?")
- Different handling for own vs captured

## Common Patterns

### Pattern 1: Transaction Boundary

Ensure all effects wait for commit:

```python
from airlock.integrations.django import DjangoScope

with transaction.atomic():
    with airlock.scope(_cls=DjangoScope):
        order.save()
        third_party_lib.process(order)  # May use nested scopes
    # Nothing dispatches yet
# All effects dispatch after commit
```

### Pattern 2: Multi-Step Atomic Operation

```python
def checkout_cart(cart_id):
    """Ensure all steps dispatch together atomically."""
    with airlock.scope():
        validate_inventory(cart_id)     # May have nested scopes
        charge_payment(cart_id)         # May have nested scopes
        send_confirmation(cart_id)      # May have nested scopes
    # All effects from all steps dispatch together
```

### Pattern 3: Batching from Nested Operations

Collect specific effects for batch processing:

```python
class EmailBatcher(Scope):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.emails = []

    def before_descendant_flushes(self, exiting_scope, intents):
        # Separate emails from other intents
        for intent in intents:
            if 'email' in intent.name:
                self.emails.append(intent)

        # Allow non-emails through
        return [i for i in intents if 'email' not in i.name]

with EmailBatcher() as batcher:
    process_bulk_orders()  # Nested code can enqueue emails
    # Non-email effects dispatched immediately

# Send all emails in one batch
send_batch_emails(batcher.emails)
```

### Pattern 4: Ordering Control

Ensure effects execute in the right order:

```python
class DBBeforeCacheScope(Scope):
    """DB writes execute now, cache updates execute later."""

    def before_descendant_flushes(self, exiting_scope, intents):
        # Let DB writes through immediately
        db_writes = [i for i in intents if 'db' in i.name]
        return db_writes

with DBBeforeCacheScope():
    with airlock.scope():
        airlock.enqueue(db_write)
        airlock.enqueue(update_cache)
    # db_write executes here (allowed through)

# update_cache executes here (was captured)
```

### Pattern 5: Independent Nested Scopes (Opt-Out)

Allow nested scopes to flush independently:

```python
class IndependentScope(Scope):
    def before_descendant_flushes(self, exiting_scope, intents):
        return intents  # Allow all through

with IndependentScope():
    with airlock.scope():
        airlock.enqueue(task)
    # task dispatches here (not captured)
```

**Use sparingly** - breaks compositional safety!

## Inspecting Nested Behavior

### Check if intent is captured

```python
with airlock.scope() as outer:
    airlock.enqueue(task_a)

    with airlock.scope() as inner:
        airlock.enqueue(task_b)

    # task_b is in outer's captured_intents
    assert task_b_intent in outer.captured_intents
```

### Audit nested dispatch

```python
with airlock.scope() as s:
    complex_operation()

    print(f"Total effects: {len(s.intents)}")
    print(f"From this scope: {len(s.own_intents)}")
    print(f"From nested scopes: {len(s.captured_intents)}")
```

## Policy Inheritance

Nested scopes inherit policy from parent? **No**, each scope has its own policy:

```python
with airlock.scope(policy=DropAll()):
    airlock.enqueue(task_a)  # Dropped by outer policy

    with airlock.scope(policy=AllowAll()):
        airlock.enqueue(task_b)  # Allowed by inner policy, captured by outer
    # Inner scope would flush task_b, but outer captures it

# Outer scope applies DropAll to captured task_b
# Result: Both task_a and task_b dropped
```

Each scope's policy applies to its **own flush decision**, but captured intents are subject to the parent's policy when the parent flushes.

## Testing with Nested Scopes

### Test that library uses scopes

```python
def test_library_buffers_effects():
    with airlock.scope() as s:
        third_party_lib.do_something()

    # Verify library buffered effects (via nested scopes)
    assert len(s.captured_intents) > 0
```

### Test atomic behavior

```python
def test_checkout_is_atomic():
    with airlock.scope() as s:
        checkout_cart(123)

    # All steps buffered together
    assert len(s.intents) >= 3  # inventory + payment + email
```

