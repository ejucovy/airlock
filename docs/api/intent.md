# Intent API

The `Intent` class represents a buffered side effect.

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `task` | `Callable` | The callable to execute |
| `args` | `tuple` | Positional arguments |
| `kwargs` | `dict` | Keyword arguments |
| `name` | `str` | Derived name for logging/filtering |
| `origin` | `str \| None` | Optional origin metadata |
| `dispatch_options` | `dict \| None` | Queue-specific options (countdown, queue, etc.) |
| `local_policies` | `tuple[Policy, ...]` | Captured policy stack from `airlock.policy()` |

## Methods

### passes_local_policies()

Check if this intent passes its captured local policies.

```python
def passes_local_policies(self) -> bool:
    """
    Returns:
        True if intent passes all local policies, False otherwise
    """
```

**Example:**

```python
with airlock.scope() as s:
    airlock.enqueue(task_a)  # No local policies

    with airlock.policy(airlock.DropAll()):
        airlock.enqueue(task_b)  # Captured DropAll

    intent_a, intent_b = s.intents

    assert intent_a.passes_local_policies() is True   # No policies
    assert intent_b.passes_local_policies() is False  # DropAll blocks
```

**Note:** This only checks **local policies** (from `airlock.policy()`). It does NOT check:
- Scope-level policy
- Whether scope will flush or discard
- Dispatch execution success

## Intent Name

The `name` property is derived from the task:

```python
# Function
def my_task():
    pass

intent = Intent(task=my_task, ...)
assert intent.name == "my_task"

# Celery task
@app.task
def celery_task():
    pass

intent = Intent(task=celery_task, ...)
assert intent.name == "celery_task"

# Lambda (gets generic name)
intent = Intent(task=lambda: None, ...)
assert intent.name == "<lambda>"
```

Used for:
- Logging
- Policy filtering (e.g., `BlockTasks({"my_task"})`)
- Debugging

## Creating Intents

You typically don't create intents directly - use `airlock.enqueue()`:

```python
airlock.enqueue(my_task, arg1, arg2, kwarg=value)
# Creates: Intent(task=my_task, args=(arg1, arg2), kwargs={"kwarg": value})
```

But you can create them manually for testing:

```python
from airlock import Intent

intent = Intent(
    task=my_task,
    args=(1, 2),
    kwargs={"foo": "bar"},
    origin="test",
    dispatch_options={"queue": "high"},
    local_policies=()
)
```

## Dispatch Options

Options are passed through to the executor:

```python
# Celery executor
airlock.enqueue(
    celery_task,
    arg,
    _dispatch_options={"countdown": 60, "queue": "emails"}
)
# Calls: celery_task.apply_async(args=(arg,), countdown=60, queue="emails")

# django-q executor
airlock.enqueue(
    task,
    arg,
    _dispatch_options={"group": "batch", "timeout": 300}
)
# Calls: async_task(task, arg, group="batch", timeout=300)
```

Options are executor-specific.

## Local Policies

Policies captured via `airlock.policy()`:

```python
with airlock.scope() as s:
    with airlock.policy(airlock.BlockTasks({"foo"})):
        with airlock.policy(airlock.LogOnFlush()):
            airlock.enqueue(task)

intent = s.intents[0]
assert len(intent.local_policies) == 2
# [BlockTasks(...), LogOnFlush(...)]
```

Policies are evaluated **innermost first** at flush time.

## Provenance (origin)

Optional metadata for debugging:

```python
airlock.enqueue(task, _origin="checkout_flow:step_3")

# Later inspection
for intent in scope.intents:
    print(f"{intent.name} from {intent.origin}")
```

## Immutability

Intents are **frozen** after creation - you cannot modify them:

```python
intent.args = (new_args,)  # Error: can't set attribute
```

This ensures policies can't mutate intents.

## Example: Testing

```python
def test_order_processing():
    with airlock.scope() as s:
        process_order(123)

    # Inspect buffered intents
    assert len(s.intents) == 2

    email_intent = s.intents[0]
    assert email_intent.name == "send_confirmation_email"
    assert email_intent.args == ()
    assert email_intent.kwargs == {"order_id": 123}

    warehouse_intent = s.intents[1]
    assert warehouse_intent.name == "notify_warehouse"
    assert warehouse_intent.kwargs == {"order_id": 123}
```

## Example: Custom Policy Using Intent

```python
class PriorityFilter(Policy):
    def allows(self, intent: Intent) -> bool:
        # Filter based on dispatch options
        priority = intent.dispatch_options.get("priority", 0)
        return priority >= 5

with airlock.scope(policy=PriorityFilter()):
    airlock.enqueue(low, _dispatch_options={"priority": 1})   # Dropped
    airlock.enqueue(high, _dispatch_options={"priority": 10}) # Dispatches
```

