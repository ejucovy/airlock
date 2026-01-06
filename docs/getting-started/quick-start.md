# Quick Start

## Basic Usage

```python
import airlock

from my_app.tasks import send_email, sync_to_warehouse

# 1. Domain code expresses intent (no .delay() calls)
def do_business_logic():
    # ...
    airlock.enqueue(send_email, user_id=123)
    airlock.enqueue(sync_to_warehouse, item_id=456)

# 2. Scope controls what escapes
with airlock.scope():
    do_business_logic()
# side effects dispatch when scope exits
```

## Using Policies

Control what escapes:

```python
# Allow everything (default)
airlock.scope(policy=airlock.AllowAll())

# Drop everything silently
airlock.scope(policy=airlock.DropAll())

# Raise if anything is enqueued
airlock.scope(policy=airlock.AssertNoEffects())

# Block specific tasks by name
airlock.scope(policy=airlock.BlockTasks({"myapp.tasks:send_sms"}))

# Log everything at flush time
airlock.scope(policy=airlock.LogOnFlush())

# Combine policies
airlock.scope(policy=airlock.CompositePolicy(
    airlock.LogOnFlush(),
    airlock.BlockTasks({"myapp.tasks:expensive_rebuild"}),
))
```

## Local Policy Contexts

Sometimes you need policy control over a *region* of code without creating a separate buffer. Use `airlock.policy()`:

```python
def do_business_logic():
    # ...
    airlock.enqueue(task_b)
    airlock.enqueue(task_c)

with airlock.scope():
    airlock.enqueue(task_a)

    with airlock.policy(airlock.DropAll()):
        do_business_logic()

    airlock.enqueue(task_d)

# when scope exits, task_a and task_d will dispatch, task_b and task_c won't
```

All four intents go to the **same buffer**. The policy is captured on each intent at enqueue time and applied at flush.

This differs from nested scopes, which create separate buffers. By default, parent scopes capture nested scope intents (see [Nested Scopes](../concepts/nested-scopes.md)).

## Next Steps

- [Understand the Problem](../concepts/problem.md) - Why airlock exists
- [Policies Deep Dive](../concepts/policies.md) - Learn about policy patterns
- [Django Integration](../integrations/django.md) - Set up automatic scoping
