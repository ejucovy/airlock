# Testing Guide

Airlock makes testing side effects straightforward. You can suppress them, assert they don't happen, or inspect what would have been dispatched.

## Quick Reference

| Goal | Policy |
|------|--------|
| Suppress all side effects | `DropAll()` |
| Fail if any side effect is enqueued | `AssertNoEffects()` |
| Inspect what was enqueued | `DropAll()` + `scope.intents` |
| Block specific tasks | `BlockTasks({"task_name"})` |
| Let side effects run normally | `AllowAll()` (default) |

## Suppressing Side Effects

Use `DropAll()` to test business logic without triggering external systems:

```python
import airlock

def test_order_processing():
    with airlock.scope(policy=airlock.DropAll()):
        order = Order.create(user, cart)
        order.process()
        assert order.status == "processed"
    # No emails sent, no warehouse notified
```

## Asserting No Side Effects

Use `AssertNoEffects()` when code should be pure:

```python
def test_calculate_total_is_pure():
    with airlock.scope(policy=airlock.AssertNoEffects()):
        total = calculate_order_total(order)
        assert total == 99.99
    # Raises PolicyViolation if calculate_order_total() calls enqueue()
```

## Inspecting Enqueued Intents

Use `scope.intents` to inspect what would have been dispatched:

```python
def test_order_enqueues_expected_tasks():
    with airlock.scope(policy=airlock.DropAll()) as scope:
        order = Order(id=42)
        order.process()

    # Check which tasks were enqueued
    intent_names = [i.name for i in scope.intents]
    assert intent_names == ["send_confirmation_email", "notify_warehouse"]

    # Check arguments
    email_intent = scope.intents[0]
    assert email_intent.kwargs["order_id"] == 42
```

Each `Intent` object has:

- `intent.name` - The task function name
- `intent.task` - The actual callable
- `intent.args` - Positional arguments tuple
- `intent.kwargs` - Keyword arguments dict
- `intent.dispatch_options` - Options passed via `_dispatch_options`

## Pytest Fixture

To suppress side effects across all tests, add an autouse fixture to `conftest.py`:

```python
import pytest
import airlock

@pytest.fixture(autouse=True)
def suppress_side_effects():
    with airlock.scope(policy=airlock.DropAll()) as scope:
        yield scope
```

Tests can then inspect `scope.intents` when needed by requesting the fixture explicitly:

```python
def test_notifications(suppress_side_effects):
    order.process()
    assert len(suppress_side_effects.intents) == 2
```

## Reset Configuration Between Tests

If tests modify global configuration, reset it:

```python
@pytest.fixture(autouse=True)
def reset_airlock_config():
    yield
    airlock.reset_configuration()
```
