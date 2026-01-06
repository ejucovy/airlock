# Policies

Policies control **what** escapes from a scope. They act as filters and observers on side effects.

## Built-in Policies

### AllowAll (default)

Allows everything through:

```python
with airlock.scope(policy=airlock.AllowAll()):
    airlock.enqueue(any_task)  # Dispatches
```

### DropAll

Silently drops all side effects:

```python
with airlock.scope(policy=airlock.DropAll()):
    airlock.enqueue(send_email)  # Buffered but never dispatched
```

Useful for:
- Dry-run modes in scripts
- Testing without side effects
- Read-only operations that reuse business logic

### AssertNoEffects

Raises `PolicyViolation` if any side effect is attempted:

```python
with airlock.scope(policy=airlock.AssertNoEffects()):
    pure_calculation()  # OK
    airlock.enqueue(task)  # Raises PolicyViolation immediately
```

Useful for:
- Test assertions
- Ensuring code paths are pure
- Catching unexpected side effects

### BlockTasks

Blocks specific tasks by name:

```python
# Block silently
policy = airlock.BlockTasks({"myapp.tasks:send_email", "myapp.tasks:send_sms"})

with airlock.scope(policy=policy):
    airlock.enqueue(send_email)  # Dropped
    airlock.enqueue(log_event)   # Dispatches
```

Block and raise immediately:

```python
policy = airlock.BlockTasks({"dangerous_task"}, raise_on_enqueue=True)

with airlock.scope(policy=policy):
    airlock.enqueue(dangerous_task)  # Raises PolicyViolation
```

Useful for:
- Selective suppression in backfills
- Preventing specific tasks in certain contexts
- Gradual feature rollout

### LogOnFlush

Logs all side effects at flush time:

```python
import logging
logger = logging.getLogger(__name__)

with airlock.scope(policy=airlock.LogOnFlush(logger)):
    airlock.enqueue(task_a)
    airlock.enqueue(task_b)
# Logs: "Flushing intent: task_a" and "Flushing intent: task_b"
```

Useful for:
- Debugging
- Audit trails
- Observability

### CompositePolicy

Combines multiple policies:

```python
policy = airlock.CompositePolicy(
    airlock.LogOnFlush(logger),
    airlock.BlockTasks({"expensive_task"}),
)

with airlock.scope(policy=policy):
    airlock.enqueue(cheap_task)      # Logged and dispatched
    airlock.enqueue(expensive_task)  # Logged but blocked
```

All policies must allow for the intent to execute.

## Local Policy Contexts

Use `airlock.policy()` to apply policies to a region without creating a new scope:

```python
with airlock.scope():
    airlock.enqueue(task_a)  # Will dispatch

    with airlock.policy(airlock.DropAll()):
        airlock.enqueue(task_b)  # Won't dispatch

    airlock.enqueue(task_c)  # Will dispatch
```

All intents go to the same buffer. The policy is captured at enqueue time.

### Use Cases

**Suppress effects in read-only operations:**

```python
def view_order(request, order_id):
    order = Order.objects.get(id=order_id)

    with airlock.policy(airlock.DropAll()):
        # Reuse business logic but suppress any side effects
        summary = generate_order_summary(order)

    return render(request, "order.html", {"summary": summary})
```

**Block specific tasks in a region:**

```python
def backfill_orders(orders):
    for order in orders:
        with airlock.policy(airlock.BlockTasks({"myapp.tasks:send_email"})):
            # Process normally but don't spam customers
            process_order(order)
```

**Nested policies stack (innermost runs first):**

```python
with airlock.policy(airlock.LogOnFlush()):
    with airlock.policy(airlock.BlockTasks({"notifications"})):
        airlock.enqueue(send_notification)  # blocked, then logged
```

## Next Steps

- [Custom Policies](../advanced/custom-policies.md) - Write your own policies
- [Nested Scopes](nested-scopes.md) - Understand scope composition
