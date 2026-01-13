# Custom Policies

Write your own policies to implement custom filtering, validation, and observation logic.

## The Policy Protocol

```python
class Policy:
    def on_enqueue(self, intent: Intent) -> None:
        """
        Called when intent is added to buffer.
        Observe or raise. Return value ignored.
        """
        pass

    def allows(self, intent: Intent) -> bool:
        """
        Called at flush time.
        Return True to dispatch, False to drop.
        """
        return True
```

## Example: Rate Limiting

```python
class RateLimitPolicy:
    def __init__(self, max_per_flush: int):
        self.max = max_per_flush
        self._count = 0

    def on_enqueue(self, intent):
        pass

    def allows(self, intent):
        if self._count >= self.max:
            return False
        self._count += 1
        return True

with airlock.scope(policy=RateLimitPolicy(max_per_flush=10)):
    for i in range(100):
        airlock.enqueue(task, i)
# Only first 10 dispatch
```

## When to Raise vs Return False

**Raise in `on_enqueue()`** for fail-fast feedback:

```python
def on_enqueue(self, intent):
    if "dangerous" in intent.name:
        raise PolicyViolation(f"Dangerous task blocked: {intent.name}")
```

Stack trace points to the `enqueue()` call site. Good for catching bugs.

**Return False in `allows()`** for silent filtering:

```python
def allows(self, intent):
    if "dangerous" in intent.name:
        return False  # Silently drop
    return True
```

No error, no trace. Good for production filtering.

## Combining Policies

Create a simple composite:

```python
class CompositePolicy:
    def __init__(self, *policies):
        self.policies = policies

    def on_enqueue(self, intent):
        for p in self.policies:
            p.on_enqueue(intent)

    def allows(self, intent):
        return all(p.allows(intent) for p in self.policies)

policy = CompositePolicy(
    RateLimitPolicy(max_per_flush=100),
    MetricsPolicy(),
    AuditPolicy("audit.log"),
)
```

Each policy's `allows()` is called. If any returns `False`, the intent is dropped.

## Important Constraints

### Cannot Call enqueue() from Policy

```python
class BadPolicy:
    def on_enqueue(self, intent):
        airlock.enqueue(log_task)  # Raises PolicyEnqueueError!
```

This prevents infinite loops. If you need to trigger side effects from a policy, use a custom scope instead.

### Cannot Reorder Intents

Policies are per-intent boolean gates. They can't reorder. For reordering, override `Scope._dispatch_all()`.
