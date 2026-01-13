# Testing Guide

Airlock makes testing side effects straightforward. You can suppress them, assert they don't happen, or inspect what would have been dispatched.

## Quick Reference

| Goal | Policy |
|------|--------|
| Suppress all side effects | `DropAll()` |
| Fail if any side effect is enqueued | `AssertNoEffects()` |
| Inspect what was enqueued | `DropAll()` + `scope.intents` |
| Block specific tasks | `BlockTasks({"mymodule:task_name"})` (uses fully qualified names) |
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

        # Check for tasks by looking for the function name within the fully qualified name
        assert any("send_confirmation_email" in i.name for i in scope.intents)
        assert any("notify_warehouse" in i.name for i in scope.intents)

        # Check arguments
        email_intent = next(i for i in scope.intents if "send_confirmation_email" in i.name)
        assert email_intent.kwargs["order_id"] == order.id
```

### Intent properties

Each `Intent` object has:

- `intent.name` - The fully qualified task name (e.g., `"mymodule:send_email"`). Use `"func_name" in intent.name` to match by function name.
- `intent.task` - The actual callable
- `intent.args` - Positional arguments tuple
- `intent.kwargs` - Keyword arguments dict
- `intent.dispatch_options` - Options passed via `_dispatch_options`

## Testing with Specific Policies

### Block specific tasks

`BlockTasks` matches against the fully qualified task name (e.g., `"mymodule:function_name"`):

```python
def test_order_without_email():
    # Use the fully qualified name: "module:function"
    blocked = {"myapp.tasks:send_confirmation_email"}
    with airlock.scope(policy=airlock.BlockTasks(blocked)) as scope:
        order.process()

        # Email was enqueued but will be dropped
        assert any("send_confirmation_email" in i.name for i in scope.intents)
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

## Django Test Integration

When using Django with airlock, tests typically need the scope fixture:

```python
# conftest.py
import pytest
import airlock

@pytest.fixture(autouse=True)
def airlock_test_scope():
    """Wrap all tests in a scope that suppresses side effects."""
    with airlock.scope(policy=airlock.DropAll()):
        yield

# tests/test_views.py
from django.test import Client

def test_checkout_view(client):
    response = client.post("/checkout/", {"order_id": 1})
    assert response.status_code == 200
    # Side effects from the view are suppressed
```

For integration tests that need real task execution:

```python
@pytest.mark.django_db(transaction=True)
def test_full_checkout_flow(allow_side_effects, celery_worker):
    """Integration test with real Celery tasks."""
    response = client.post("/checkout/", {"order_id": 1})
    # Tasks actually dispatch to Celery
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

### Pattern 2: Parameterized policy tests

```python
import pytest

@pytest.mark.parametrize("policy,expected_count", [
    (airlock.AllowAll(), 2),
    (airlock.BlockTasks({"myapp.tasks:send_email"}), 1),
    (airlock.DropAll(), 0),
])
def test_policy_behavior(policy, expected_count, mocker):
    executor = mocker.Mock()
    with airlock.scope(policy=policy, executor=executor):
        order.process()
    assert executor.call_count == expected_count
```

### Pattern 3: Test that specific args are passed

```python
def test_email_contains_order_id():
    with airlock.scope(policy=airlock.DropAll()) as scope:
        order = Order(id=42)
        order.process()

        email_intent = next(
            i for i in scope.intents
            if "send_confirmation_email" in i.name
        )
        assert email_intent.kwargs["order_id"] == 42
```
