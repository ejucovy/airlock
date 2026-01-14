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
        return True

with airlock.scope(_cls=AlwaysFlushScope):
    airlock.enqueue(send_alert, severity="info")
    raise Exception("Something broke")
    # send_alert still dispatches despite exception
```

## Example: Deferred Dispatch (Django on_commit)

```python
from django.db import transaction

class DjangoScope(Scope):
    """Defer dispatch until transaction commits."""

    def _dispatch_all(self, intents: list[Intent]) -> None:
        def do_dispatch():
            for intent in intents:
                _execute(intent)

        transaction.on_commit(do_dispatch)

with transaction.atomic():
    with airlock.scope(_cls=DjangoScope):
        order.save()
        airlock.enqueue(send_email, order.id)
# Email dispatches after commit
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

```
1. __init__()         - Scope created
2. enter()            - Scope activated (context var set)
3. [intents buffered] - Code executes, enqueue() calls buffered
4. exit()             - Scope deactivated (context var reset)
5. should_flush()     - Decide terminal action
6. flush()            - Apply policy, call _dispatch_all()
7. _dispatch_all()    - Execute intents
```

## Why Override `_dispatch_all`, Not `flush`?

Many frameworks have a "split lifecycle" where the code block ends before the transaction commits:

- **Logical end**: The `with` block exits. No more intents should be accepted.
- **Physical end**: The transaction commits. Side effects should actually happen.

If you override `flush()` to defer execution, you create a "zombie scope"—logically finished but physically still open. This leads to bugs: double-flushes, lost intents, or intents accepted after the block exits.

The `Scope` class handles this with the Template Method pattern:

```python
def flush(self):
    # 1. Marks scope as flushed (closed to new intents)
    # 2. Applies policies synchronously
    # 3. Persists to storage
    # 4. Calls self._dispatch_all(intents)
```

By overriding only `_dispatch_all`, you defer the network calls while airlock handles the state management correctly.

## Common Mistakes

### Don't Override flush()

```python
# Bad - breaks internal state management
class BadScope(Scope):
    def flush(self):
        ...
```

Override `should_flush()` or `_dispatch_all()` instead.

### Don't Forget to Call super()

```python
# Bad - breaks buffer management
class BadScope(Scope):
    def _add(self, intent):
        my_custom_buffer.append(intent)  # Forgot super()!

# Good
class GoodScope(Scope):
    def _add(self, intent):
        super()._add(intent)
        my_custom_buffer.append(intent)
```

### Don't Mutate Intents List

```python
# Bad - mutates caller's list
def before_descendant_flushes(self, exiting_scope, intents):
    intents.append(new_intent)
    return intents

# Good - return new list
def before_descendant_flushes(self, exiting_scope, intents):
    return intents + [new_intent]
```
