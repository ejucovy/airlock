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

Use `DropAll()` to silently suppress all side effects:

```python
import airlock

def test_order_processing():
    with airlock.scope(policy=airlock.DropAll()):
        order = Order.create(user, cart)
        order.process()

        assert order.status == "processed"
    # No emails sent, no warehouse notified
```

This is useful when you want to test business logic without triggering external systems.

## Asserting No Side Effects

Use `AssertNoEffects()` when code should be pure:

```python
import airlock
import pytest

def test_calculate_total_is_pure():
    with airlock.scope(policy=airlock.AssertNoEffects()):
        total = calculate_order_total(order)
        assert total == 99.99
    # Raises if calculate_order_total() calls enqueue()
```

This catches accidental side effects in code that should be pure computation.

## Inspecting Enqueued Intents

Combine `DropAll()` with `scope.intents` to inspect what would have been dispatched:

```python
import airlock

def test_order_sends_correct_notifications():
    with airlock.scope(policy=airlock.DropAll()) as scope:
        order = Order.create(user, cart)
        order.process()

        # Inspect the buffered intents
        assert len(scope.intents) == 2

        intent_names = [intent.name for intent in scope.intents]
        assert "send_confirmation_email" in intent_names
        assert "notify_warehouse" in intent_names

        # Check arguments
        email_intent = next(i for i in scope.intents if i.name == "send_confirmation_email")
        assert email_intent.kwargs["order_id"] == order.id
```

### Intent properties

Each `Intent` object has:

- `intent.name` - The task function name
- `intent.task` - The actual callable
- `intent.args` - Positional arguments tuple
- `intent.kwargs` - Keyword arguments dict
- `intent.dispatch_options` - Options passed via `_dispatch_options`

## Testing with Specific Policies

### Block specific tasks

```python
def test_order_without_email():
    with airlock.scope(policy=airlock.BlockTasks({"send_confirmation_email"})) as scope:
        order.process()

        # Email was enqueued but will be dropped
        assert any(i.name == "send_confirmation_email" for i in scope.intents)
    # Warehouse notification dispatches, email does not
```

### Custom test policy

```python
class RecordingPolicy:
    def __init__(self):
        self.enqueued = []
        self.dispatched = []

    def on_enqueue(self, intent):
        self.enqueued.append(intent)

    def allows(self, intent):
        self.dispatched.append(intent)
        return False  # Don't actually dispatch

def test_with_recording():
    policy = RecordingPolicy()
    with airlock.scope(policy=policy):
        order.process()

    assert len(policy.enqueued) == 2
    assert len(policy.dispatched) == 2
```

## Pytest Fixtures

### Global suppression fixture

```python
# conftest.py
import pytest
import airlock

@pytest.fixture(autouse=True)
def suppress_side_effects():
    """Suppress all side effects by default in tests."""
    with airlock.scope(policy=airlock.DropAll()):
        yield

# All tests automatically run inside a DropAll scope
def test_something():
    order.process()  # Side effects suppressed
```

### Opt-in fixture for inspecting intents

```python
# conftest.py
import pytest
import airlock

@pytest.fixture
def airlock_scope():
    """Provide a scope for inspecting intents."""
    with airlock.scope(policy=airlock.DropAll()) as scope:
        yield scope

# Usage
def test_notifications(airlock_scope):
    order.process()
    assert len(airlock_scope.intents) == 2
```

### Fixture for allowing side effects

```python
# conftest.py
import pytest
import airlock

@pytest.fixture
def allow_side_effects():
    """Allow side effects (for integration tests)."""
    with airlock.scope(policy=airlock.AllowAll()):
        yield
```

## Testing Without Scopes

If your code uses `airlock.enqueue()` outside of any scope, it raises `NoScopeError`:

```python
import airlock
import pytest

def test_enqueue_without_scope():
    with pytest.raises(airlock.NoScopeError):
        airlock.enqueue(some_task)
```

This is intentional - airlock requires explicit scope boundaries.

## Reset Configuration Between Tests

If tests modify global configuration, reset it:

```python
# conftest.py
import pytest
import airlock

@pytest.fixture(autouse=True)
def reset_airlock_config():
    yield
    airlock.reset_configuration()
```

## Common Testing Patterns

### Pattern 1: Test business logic, then test side effects separately

```python
def test_order_status_updated():
    """Test the business logic only."""
    with airlock.scope(policy=airlock.DropAll()):
        order.process()
        assert order.status == "processed"

def test_order_triggers_notifications():
    """Test the side effect intents."""
    with airlock.scope(policy=airlock.DropAll()) as scope:
        order.process()
        assert len(scope.intents) == 2
```

### Pattern 2: Test that specific args are passed

```python
def test_email_contains_order_id():
    with airlock.scope(policy=airlock.DropAll()) as scope:
        order = Order(id=42)
        order.process()

        email_intent = next(
            i for i in scope.intents
            if i.name == "send_confirmation_email"
        )
        assert email_intent.kwargs["order_id"] == 42
```
