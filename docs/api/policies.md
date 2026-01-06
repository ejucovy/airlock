# Policies API Reference

Built-in policies for controlling side effect execution.

## AllowAll

Allows all intents (default).

```python
class AllowAll(Policy)
```

**Example:**

```python
with airlock.scope(policy=airlock.AllowAll()):
    airlock.enqueue(anything)  # Always dispatches
```

## DropAll

Silently drops all intents.

```python
class DropAll(Policy)
```

**Example:**

```python
with airlock.scope(policy=airlock.DropAll()):
    airlock.enqueue(task)  # Buffered but never dispatched
```

## AssertNoEffects

Raises `PolicyViolation` if any intent is enqueued.

```python
class AssertNoEffects(Policy)
```

**Raises:** `PolicyViolation` immediately on any `enqueue()` call.

**Example:**

```python
with airlock.scope(policy=airlock.AssertNoEffects()):
    pure_function()  # OK
    airlock.enqueue(task)  # Raises PolicyViolation
```

## BlockTasks

Blocks specific tasks by name.

```python
class BlockTasks(Policy):
    def __init__(
        self,
        blocked_names: Set[str],
        raise_on_enqueue: bool = False
    )
```

**Parameters:**

- `blocked_names` (Set[str]) - Set of task names to block
- `raise_on_enqueue` (bool) - If `True`, raise on enqueue. If `False`, silently drop at flush.

**Example:**

```python
# Silent drop
policy = airlock.BlockTasks({"send_email", "send_sms"})

# Fail fast
policy = airlock.BlockTasks({"dangerous_task"}, raise_on_enqueue=True)
```

## LogOnFlush

Logs all intents at flush time.

```python
class LogOnFlush(Policy):
    def __init__(self, logger: logging.Logger | None = None)
```

**Parameters:**

- `logger` (Logger | None) - Logger to use. If None, uses default logger.

**Example:**

```python
import logging
logger = logging.getLogger(__name__)

with airlock.scope(policy=airlock.LogOnFlush(logger)):
    airlock.enqueue(task_a)
    airlock.enqueue(task_b)
# Logs: "Flushing intent: task_a"
# Logs: "Flushing intent: task_b"
```

## CompositePolicy

Combines multiple policies.

```python
class CompositePolicy(Policy):
    def __init__(self, *policies: Policy)
```

**Parameters:**

- `*policies` (Policy) - Policies to combine

**Behavior:** All policies must allow for intent to execute. If any policy returns `False` from `allows()`, the intent is dropped.

**Example:**

```python
policy = airlock.CompositePolicy(
    airlock.LogOnFlush(logger),
    airlock.BlockTasks({"expensive_task"}),
)

with airlock.scope(policy=policy):
    airlock.enqueue(cheap_task)      # Logged + dispatched
    airlock.enqueue(expensive_task)  # Logged but blocked
```

## Policy Protocol

To write custom policies, implement this protocol:

```python
class Policy(Protocol):
    def on_enqueue(self, intent: Intent) -> None:
        """
        Called when intent is added to buffer.
        Observe or raise. Return value ignored.
        """
        ...

    def allows(self, intent: Intent) -> bool:
        """
        Called at flush time.
        Return True to dispatch, False to drop.
        """
        ...
```

See [Custom Policies](../extending/custom-policies.md) for examples.

## Next Steps

- [Custom Policies Guide](../extending/custom-policies.md) - Write your own policies
- [Core API](core.md) - Main airlock functions
- [Intent API](intent.md) - Intent class reference
