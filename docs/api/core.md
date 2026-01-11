# Core API Reference

The main functions you'll use in application code.

## airlock.scope()

Create a lifecycle boundary for side effects.

```python
airlock.scope(
    policy=None,
    executor=None,
    *,
    _cls=Scope
) -> ContextManager[Scope]
```

**Parameters:**

- `policy` (Policy | None) - Policy controlling what intents are allowed. Defaults to `AllowAll()`.
- `executor` (Callable | None) - Executor for dispatching intents. Defaults to `sync_executor`.
- `_cls` (Type[Scope]) - Scope class to use. For custom scope subclasses.

**Returns:** Context manager yielding the scope instance.

**Example:**

```python
with airlock.scope() as s:
    airlock.enqueue(task_a)
    airlock.enqueue(task_b)
# Effects dispatch here
```

**With custom scope:**

```python
from airlock.integrations.django import DjangoScope

with airlock.scope(_cls=DjangoScope):
    airlock.enqueue(task)
```

## airlock.enqueue()

Express intent to perform a side effect.

```python
airlock.enqueue(
    task: Callable,
    *args,
    _origin: str | None = None,
    _dispatch_options: dict | None = None,
    **kwargs
) -> None
```

**Parameters:**

- `task` (Callable) - The callable to execute (Celery task, function, etc.)
- `*args` - Positional arguments for the task
- `_origin` (str | None) - Optional origin metadata for debugging
- `_dispatch_options` (dict | None) - Optional dispatch options (countdown, queue, etc.)
- `**kwargs` - Keyword arguments for the task

**Raises:**

- `NoScopeError` - If no scope is active
- `PolicyEnqueueError` - If called from within a policy callback

**Example:**

```python
airlock.enqueue(send_email, user_id=123)

airlock.enqueue(
    send_email,
    user_id=123,
    _dispatch_options={"countdown": 60, "queue": "emails"}
)
```

## airlock.policy()

Context manager for local policy control without creating a new buffer.

```python
airlock.policy(p: Policy) -> ContextManager[None]
```

**Parameters:**

- `p` (Policy) - Policy to apply to intents enqueued within this context

**Example:**

```python
with airlock.scope():
    airlock.enqueue(task_a)  # Will dispatch

    with airlock.policy(airlock.DropAll()):
        airlock.enqueue(task_b)  # Won't dispatch

    airlock.enqueue(task_c)  # Will dispatch
```

All intents go to the same buffer. Policy is captured per-intent at enqueue time.

## airlock.get_current_scope()

Get the currently active scope, or None.

```python
airlock.get_current_scope() -> Scope | None
```

**Returns:** The active scope, or `None` if no scope is active.

**Example:**

```python
scope = airlock.get_current_scope()
if scope:
    print(f"Buffered intents: {len(scope.intents)}")
else:
    print("No active scope")
```

