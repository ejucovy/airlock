# Introspection

The buffer contains everything attempted, regardless of policy. This provides a complete audit log and enables powerful debugging.

## Inspecting Intents

```python
with airlock.scope() as s:
    airlock.enqueue(task_a)

    with airlock.policy(airlock.DropAll()):
        airlock.enqueue(task_b)

    # s.intents contains both in enqueue order - complete audit log
    assert len(s.intents) == 2

    intent_a, intent_b = s.intents  # Ordered by enqueue time

    # task_a has no local policies, will dispatch
    assert intent_a.local_policies == ()
    assert intent_a.passes_local_policies() is True

    # task_b captured DropAll, won't dispatch
    assert len(intent_b.local_policies) == 1
    assert isinstance(intent_b.local_policies[0], airlock.DropAll)
    assert intent_b.passes_local_policies() is False
# When scope exits, only task_a dispatches
```

## Dispatch Semantics: Three Layers

Whether an intent actually executes depends on three independent layers:

| Layer | Question | Evaluated by |
|-------|----------|--------------|
| **Intent** | Does this intent pass its local policies? | `intent.passes_local_policies()` |
| **Scope** | Will this scope flush or discard? | Scope lifecycle |
| **Dispatch** | Does execution succeed? | `_execute()` / dispatcher |

`passes_local_policies()` only answers the first question. It does not consider scope-level policy, whether the scope flushes, or dispatch success.

## Inspecting Buffered Intents

```python
with airlock.scope() as s:
    do_stuff()

    # See what's buffered before it escapes
    for intent in s.intents:
        print(f"{intent.name}: {intent.args}, {intent.kwargs}")
```

## Intent Properties

Each intent exposes:

| Property | Type | Description |
|----------|------|-------------|
| `task` | `Callable` | The callable to execute |
| `args` | `tuple` | Positional arguments |
| `kwargs` | `dict` | Keyword arguments |
| `name` | `str` | Derived name for logging |
| `origin` | `str \| None` | Optional origin metadata |
| `dispatch_options` | `dict \| None` | Queue options (countdown, queue, etc.) |
| `local_policies` | `tuple[Policy, ...]` | Captured policy stack |

## Provenance Tracking

Parent scopes can distinguish their own intents from captured intents:

```python
with airlock.scope() as outer:
    airlock.enqueue(task_a)  # outer's own intent

    with airlock.scope() as inner:
        airlock.enqueue(task_b)  # captured from inner

    # Provenance inspection
    print(f"Own: {len(outer.own_intents)}")          # 1
    print(f"Captured: {len(outer.captured_intents)}")  # 1
    print(f"Total: {len(outer.intents)}")            # 2
```

## Use Cases

### Testing

Verify expected side effects without actually executing them:

```python
def test_order_processing():
    with airlock.scope() as s:
        process_order(order_id=123)

    # Verify expected tasks were enqueued
    assert len(s.intents) == 2
    assert s.intents[0].task.__name__ == "notify_warehouse"
    assert s.intents[1].task.__name__ == "send_confirmation"

    # Verify arguments
    assert s.intents[0].kwargs == {"order_id": 123}
```

### Debugging

Log all attempted side effects:

```python
with airlock.scope() as s:
    complex_operation()

    print("Attempted side effects:")
    for intent in s.intents:
        passed = "✓" if intent.passes_local_policies() else "✗"
        print(f"{passed} {intent.name}")
```

### Conditional Flushing

Make flush decisions based on buffered intents:

```python
class ConditionalScope(Scope):
    def should_flush(self, error):
        if error:
            return False
        # Only flush if there are high-priority intents
        return any(
            i.dispatch_options and i.dispatch_options.get("priority") == "high"
            for i in self.intents
        )
```

## Next Steps

- [API Reference: Intent](../api/intent.md) - Complete Intent API
- [Advanced: Custom Policies](../advanced/custom-policies.md) - Write policies that inspect intents
