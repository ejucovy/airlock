# Custom Scopes

Subclass `Scope` to customize lifecycle behavior: when to flush, how to dispatch, nested scope handling.

## Extension Points

| Method | Purpose | Default |
|--------|---------|---------|
| `should_flush(error)` | Decide whether to flush or discard | Flush on success, discard on error |
| `before_descendant_flushes(scope, intents)` | Control nested scope capture | Capture all |
| `_dispatch_all(intents)` | Customize dispatch mechanism | Iterate and execute |

## Example: Always Flush (Even on Error)

```python
class AlwaysFlushScope(Scope):
    """Flush even on error - for error notification patterns."""

    def should_flush(self, error: BaseException | None) -> bool:
        return True  # Always flush

# Usage
with airlock.scope(_cls=AlwaysFlushScope):
    airlock.enqueue(send_alert, severity="info")
    raise Exception("Something broke")
    # send_alert still dispatches despite exception
```

## Example: Conditional Flush

```python
class ConditionalScope(Scope):
    """Only flush if there are high-priority intents."""

    def should_flush(self, error: BaseException | None) -> bool:
        if error:
            return False

        # Only flush if at least one high-priority intent
        return any(
            i.dispatch_options and i.dispatch_options.get("priority") == "high"
            for i in self.intents
        )

with airlock.scope(_cls=ConditionalScope):
    airlock.enqueue(low_task, _dispatch_options={"priority": "low"})
    airlock.enqueue(high_task, _dispatch_options={"priority": "high"})
# Flushes because high_task is present
```

## Example: Deferred Dispatch (Django on_commit)

```python
from django.db import transaction

class DjangoScope(Scope):
    """Defer dispatch until transaction commits."""

    def _dispatch_all(self, intents: list[Intent]) -> None:
        def do_dispatch():
            # Execute dispatch after commit
            for intent in intents:
                _execute(intent)

        transaction.on_commit(do_dispatch)

# Usage
with transaction.atomic():
    with airlock.scope(_cls=DjangoScope):
        order.save()
        airlock.enqueue(send_email, order.id)
    # Email buffered, not dispatched yet
# Email dispatches here (after commit)
```

## Example: Persistent Buffer (Outbox Pattern)

```python
class OutboxScope(Scope):
    """Persist intents to database for durable buffering."""

    def _add(self, intent):
        super()._add(intent)  # Add to in-memory buffer

        # Also persist to database
        TaskOutbox.objects.create(
            task_name=intent.name,
            args=intent.args,
            kwargs=intent.kwargs,
            status='pending'
        )

    def _dispatch_all(self, intents):
        # Mark as ready instead of executing
        # Separate worker will dispatch later
        TaskOutbox.objects.filter(
            task_name__in=[i.name for i in intents],
            status='pending'
        ).update(status='ready')

# Intents survive process crashes
```

## Example: Independent Nested Scopes

```python
class IndependentScope(Scope):
    """Allow nested scopes to flush independently."""

    def before_descendant_flushes(self, exiting_scope, intents):
        return intents  # Allow all through (don't capture)

with IndependentScope():
    with airlock.scope():
        airlock.enqueue(task)
    # task dispatches here (not captured)
```

## Example: Selective Capture

```python
class SafetyScope(Scope):
    """Capture dangerous tasks, allow safe tasks through."""

    def before_descendant_flushes(self, exiting_scope, intents):
        # Allow safe tasks through
        safe = [i for i in intents if not i.dispatch_options.get("dangerous")]
        return safe

with SafetyScope():
    with airlock.scope():
        airlock.enqueue(safe_task)
        airlock.enqueue(dangerous_task, _dispatch_options={"dangerous": True})
    # safe_task executes here

# dangerous_task executes here (was captured)
```

## Example: Batching Scope

```python
class EmailBatchScope(Scope):
    """Batch emails, allow other intents through."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.email_batch = []

    def before_descendant_flushes(self, exiting_scope, intents):
        # Separate emails from others
        emails = [i for i in intents if 'email' in i.name]
        others = [i for i in intents if 'email' not in i.name]

        # Batch emails for later
        self.email_batch.extend(emails)

        # Allow others through now
        return others

with EmailBatchScope() as scope:
    process_bulk_operations()  # Nested code enqueues emails
    # Non-email effects dispatched

# Send batched emails
send_batch_emails(scope.email_batch)
```

## Available State in Subclasses

| Property | Type | Description |
|----------|------|-------------|
| `self.intents` | `list[Intent]` | All buffered intents (own + captured) |
| `self.own_intents` | `list[Intent]` | Intents from this scope |
| `self.captured_intents` | `list[Intent]` | Intents from nested scopes |
| `self._policy` | `Policy` | Scope's policy |
| `self.is_flushed` | `bool` | True after flush() called |
| `self.is_discarded` | `bool` | True after discard() called |

## Lifecycle Phases

Understanding the lifecycle helps with customization:

```
1. __init__()         - Scope created
2. enter()            - Scope activated (context var set)
3. [intents buffered] - Code executes, enqueue() calls buffered
4. exit()             - Scope deactivated (context var reset)
5. should_flush()     - Decide terminal action
6. flush()            - Apply policy, call _dispatch_all()
7. _dispatch_all()    - Execute intents
```

## Common Mistakes

### ❌ Don't Override flush()

```python
# ❌ Bad - breaks internal state management
class BadScope(Scope):
    def flush(self):
        # Custom logic
        ...
```

**Instead:** Override `should_flush()` or `_dispatch_all()`.

### ❌ Don't Forget to Call super()

```python
# ❌ Bad - breaks buffer management
class BadScope(Scope):
    def _add(self, intent):
        my_custom_buffer.append(intent)  # Forgot super()!
```

**Fix:**

```python
class GoodScope(Scope):
    def _add(self, intent):
        super()._add(intent)  # Add to internal buffer
        my_custom_buffer.append(intent)  # Plus custom logic
```

### ❌ Don't Mutate Intents List

```python
# ❌ Bad - mutates caller's list
def before_descendant_flushes(self, exiting_scope, intents):
    intents.append(new_intent)  # Mutates original!
    return intents
```

**Fix:**

```python
def before_descendant_flushes(self, exiting_scope, intents):
    return intents + [new_intent]  # Return new list
```

## Testing Custom Scopes

```python
def test_always_flush_scope():
    with airlock.scope(_cls=AlwaysFlushScope) as s:
        airlock.enqueue(task)
        raise Exception()

    # Verify it flushed despite exception
    assert s.is_flushed
    assert not s.is_discarded
```

