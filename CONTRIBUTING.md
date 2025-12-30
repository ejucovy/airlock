# Contributing to Airlock

Thank you for helping us make side effects safe!

## Development Setup

1.  Clone the repo.
2.  Create a virtual environment: `python -m venv .venv && source .venv/bin/activate`
3.  Install dependencies: `pip install -e .[dev]` (assuming dev extras exist, or just `pip install django celery pytest`)
4.  Run tests: `pytest`

## Extending Airlock

Airlock is designed to be extended. The most common extension point is the **Lifecycle Scope**.

### Implementing Custom Scopes

If you want to integrate with a new framework (e.g., FastAPI, Flask, Kafka consumer), you may need a custom `Scope`.

The base `airlock.Scope` class handles the heavy lifting of state management, policy enforcement, and persistence. Your job is usually just to define **when dispatch happens**.

#### The "Split Lifecycle" Problem

A common pattern in frameworks is that "finishing the request" and "committing the transaction" are different events.
*   **Logical Flush**: The code block exits. No more intents should be accepted.
*   **Physical Dispatch**: The transaction commits. Side effects happen.

If you try to manage this state manually by overriding `flush()`, you risk leaving the scope in a "Zombie State" (logically finished but physically open), leading to double-flushes or lost intents.

#### The Safe Way: Override `_dispatch_all`

The `Scope` class uses the Template Method pattern to prevent this.

```python
class Scope:
    def flush(self):
        # 1. Marks scope as flushed (CLOSED to new intents)
        # 2. Applies policies synchronously
        # 3. Persists to storage
        # 4. Calls self._dispatch_all(intents)
```

To implement deferred execution (like waiting for a DB commit), **only override `_dispatch_all`**:

```python
class MyFrameworkScope(Scope):
    def _dispatch_all(self, intents: list[Intent]) -> None:
        # Defer the calls to the parent's logic until the "real" end
        my_framework.on_commit(
            lambda: super()._dispatch_all(intents)
        )
```

By doing this, `airlock` guarantees that:
*   The scope is strictly marked as `flushed` immediately when the context manager exits.
*   Policies are evaluated immediately (capturing the state of the world at the end of the block).
*   Only the *network calls* to the side-effect system are deferred.

#### Do NOT override `flush()`

Unless you are radically changing how buffering works, avoid overriding `flush()`. If you must, you are responsible for:
1.  Checking `_flushed` and `_discarded`.
2.  Setting `self._flushed = True` **immediately**.
3.  Managing `_in_policy` context tokens during policy execution.
