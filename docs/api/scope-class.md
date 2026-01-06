# Scope Class API

The `Scope` class manages the lifecycle of side effect buffering and dispatch.

## Context Manager API (Recommended)

Most code should use the context manager:

```python
with airlock.scope() as s:
    airlock.enqueue(task)
# Automatic lifecycle management
```

## Scope Properties

| Property | Type | Description |
|----------|------|-------------|
| `intents` | `list[Intent]` | All buffered intents (own + captured) |
| `own_intents` | `list[Intent]` | Intents enqueued directly in this scope |
| `captured_intents` | `list[Intent]` | Intents captured from nested scopes |
| `is_flushed` | `bool` | True after `flush()` called |
| `is_discarded` | `bool` | True after `discard()` called |

**Example:**

```python
with airlock.scope() as s:
    airlock.enqueue(task_a)

    with airlock.scope():
        airlock.enqueue(task_b)

    print(f"Own: {len(s.own_intents)}")          # 1
    print(f"Captured: {len(s.captured_intents)}")  # 1
    print(f"Total: {len(s.intents)}")            # 2
```

## Subclassing API

Override these methods to customize behavior:

### should_flush(error)

Decide whether to flush or discard on scope exit.

```python
def should_flush(self, error: BaseException | None) -> bool:
    """
    Args:
        error: Exception that caused exit, or None for normal exit

    Returns:
        True to flush, False to discard

    Default: flush on success (error is None), discard on error
    """
    return error is None
```

**Example:**

```python
class AlwaysFlushScope(Scope):
    def should_flush(self, error):
        return True  # Flush even on error

with airlock.scope(_cls=AlwaysFlushScope):
    airlock.enqueue(send_alert)
    raise Exception()  # Alert still dispatches
```

### before_descendant_flushes(exiting_scope, intents)

Control what happens when nested scopes exit.

```python
def before_descendant_flushes(
    self,
    exiting_scope: Scope,
    intents: list[Intent]
) -> list[Intent]:
    """
    Args:
        exiting_scope: The nested scope that is exiting
        intents: Intents the nested scope wants to flush

    Returns:
        Intents to allow through (rest are captured)

    Default: return [] (capture all)
    """
    return []
```

**Example:**

```python
class IndependentScope(Scope):
    def before_descendant_flushes(self, exiting_scope, intents):
        return intents  # Allow all through (don't capture)

with IndependentScope():
    with airlock.scope():
        airlock.enqueue(task)
    # task dispatches here (not captured)
```

### _dispatch_all(intents)

Customize how intents are dispatched.

```python
def _dispatch_all(self, intents: list[Intent]) -> None:
    """
    Args:
        intents: Filtered intents to dispatch

    Default: iterate and execute via executor
    """
    for intent in intents:
        _execute(intent, executor=self._executor)
```

**Example:**

```python
from django.db import transaction

class DjangoScope(Scope):
    def _dispatch_all(self, intents):
        # Defer to transaction.on_commit()
        def do_dispatch():
            for intent in intents:
                _execute(intent, executor=self._executor)

        transaction.on_commit(do_dispatch)
```

## Imperative API (Advanced)

For framework integrations (middleware, task wrappers):

### enter()

Activate the scope.

```python
s = Scope()
s.enter()  # Scope is now active
```

### exit()

Deactivate the scope.

```python
s.exit()  # Scope is no longer active
# Must still call flush() or discard()
```

### flush()

Apply policy and dispatch intents.

```python
s.flush()  # Dispatches allowed intents
```

**Raises:** `ScopeStateError` if already flushed/discarded or still active.

### discard()

Drop all intents without dispatching.

```python
s.discard()  # All intents dropped
```

**Raises:** `ScopeStateError` if already flushed/discarded or still active.

### Example: Django Middleware Pattern

```python
def middleware(get_response, request):
    s = Scope()
    s.enter()

    error = None
    try:
        response = get_response(request)
    except BaseException as e:
        error = e
        raise
    finally:
        s.exit()  # Deactivate first

    # Decide terminal action
    if s.should_flush(error):
        s.flush()
    else:
        s.discard()

    return response
```

## Lifecycle States

```
Created → Entered → Exited → Flushed/Discarded
          (active)  (inactive)  (terminal)
```

**State transitions:**

- `enter()`: Created → Entered
- `exit()`: Entered → Exited
- `flush()` or `discard()`: Exited → Terminal

**Invariants:**

- Can only `enter()` once
- Can only `exit()` after `enter()`
- Can only `flush()` or `discard()` after `exit()`
- Cannot `flush()` and `discard()` (terminal states are exclusive)

## Next Steps

- [Custom Scopes Guide](../extending/custom-scopes.md) - Subclassing patterns
- [Core API](core.md) - Main airlock functions
- [Intent API](intent.md) - Intent class reference
