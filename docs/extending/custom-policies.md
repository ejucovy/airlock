# Custom Policies

Write your own policies to implement custom filtering, validation, and observation logic.

## The Policy Protocol

```python
class Policy:
    def on_enqueue(self, intent: Intent) -> None:
        """
        Called when intent is added to buffer.
        Observe or raise. Return value ignored.
        """
        pass

    def allows(self, intent: Intent) -> bool:
        """
        Called at flush time.
        Return True to dispatch, False to drop.
        """
        return True
```

## Example: Rate Limiting

```python
class RateLimitPolicy:
    def __init__(self, max_per_flush: int):
        self.max = max_per_flush
        self._count = 0

    def on_enqueue(self, intent):
        pass  # Could warn if close to limit

    def allows(self, intent):
        if self._count >= self.max:
            return False
        self._count += 1
        return True

# Usage
with airlock.scope(policy=RateLimitPolicy(max_per_flush=10)):
    for i in range(100):
        airlock.enqueue(task, i)
# Only first 10 dispatch
```

## Example: Priority Filtering

```python
class PriorityPolicy:
    def __init__(self, min_priority: int):
        self.min_priority = min_priority

    def on_enqueue(self, intent):
        pass

    def allows(self, intent):
        priority = intent.dispatch_options.get("priority", 0)
        return priority >= self.min_priority

# Usage
with airlock.scope(policy=PriorityPolicy(min_priority=5)):
    airlock.enqueue(low_task, _dispatch_options={"priority": 1})   # Dropped
    airlock.enqueue(high_task, _dispatch_options={"priority": 10}) # Dispatches
```

## Example: Metrics Collection

```python
from datadog import statsd

class MetricsPolicy:
    def on_enqueue(self, intent):
        statsd.increment(f"airlock.enqueued.{intent.name}")

    def allows(self, intent):
        statsd.increment(f"airlock.dispatched.{intent.name}")
        return True

# All intents tracked in Datadog
```

## Example: Audit Logging

```python
import json
from datetime import datetime

class AuditPolicy:
    def __init__(self, audit_file):
        self.audit_file = audit_file

    def on_enqueue(self, intent):
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "action": "enqueued",
            "task": intent.name,
            "args": intent.args,
            "kwargs": intent.kwargs,
        }
        with open(self.audit_file, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def allows(self, intent):
        # Log again at dispatch
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "action": "dispatched",
            "task": intent.name,
        }
        with open(self.audit_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
        return True
```

## Example: Sampling

```python
import random

class SamplingPolicy:
    def __init__(self, sample_rate: float):
        self.sample_rate = sample_rate

    def on_enqueue(self, intent):
        pass

    def allows(self, intent):
        return random.random() < self.sample_rate

# Only dispatch 10% of effects
with airlock.scope(policy=SamplingPolicy(0.1)):
    for i in range(1000):
        airlock.enqueue(analytics_task, i)
# ~100 dispatch
```

## Example: Circuit Breaker

```python
class CircuitBreakerPolicy:
    def __init__(self, error_threshold: int = 5):
        self.error_threshold = error_threshold
        self.error_count = 0
        self.is_open = False

    def on_enqueue(self, intent):
        if self.is_open:
            raise PolicyViolation("Circuit breaker is OPEN - too many errors")

    def allows(self, intent):
        return not self.is_open

    def record_error(self):
        self.error_count += 1
        if self.error_count >= self.error_threshold:
            self.is_open = True

    def reset(self):
        self.error_count = 0
        self.is_open = False
```

## When to Raise vs Return False

**Raise in `on_enqueue()`** for fail-fast feedback:

```python
def on_enqueue(self, intent):
    if "dangerous" in intent.name:
        raise PolicyViolation(f"Dangerous task blocked: {intent.name}")
```

Stack trace points to the `enqueue()` call site. Good for catching bugs.

**Return False in `allows()`** for silent filtering:

```python
def allows(self, intent):
    if "dangerous" in intent.name:
        return False  # Silently drop
    return True
```

No error, no trace. Good for production filtering.

## Stateful Policies

Policies can maintain state:

```python
class CountingPolicy:
    def __init__(self):
        self.enqueued = 0
        self.dispatched = 0

    def on_enqueue(self, intent):
        self.enqueued += 1

    def allows(self, intent):
        self.dispatched += 1
        return True

with airlock.scope(policy=CountingPolicy()) as s:
    for i in range(10):
        airlock.enqueue(task, i)

print(f"Enqueued: {s._policy.enqueued}")    # 10
print(f"Dispatched: {s._policy.dispatched}")  # 10
```

## Combining Policies

Use `CompositePolicy`:

```python
policy = airlock.CompositePolicy(
    RateLimitPolicy(max_per_flush=100),
    MetricsPolicy(),
    AuditPolicy("audit.log"),
)
```

Each policy's `allows()` is called. If any returns `False`, the intent is dropped.

## Testing Custom Policies

```python
def test_priority_policy():
    policy = PriorityPolicy(min_priority=5)

    low_intent = Intent(task=my_task, args=(), kwargs={}, dispatch_options={"priority": 1})
    high_intent = Intent(task=my_task, args=(), kwargs={}, dispatch_options={"priority": 10})

    assert policy.allows(low_intent) is False
    assert policy.allows(high_intent) is True
```

## Common Patterns

### Pattern 1: Environment-Based Behavior

```python
class EnvPolicy:
    def allows(self, intent):
        if settings.ENV == "development":
            return False  # Drop all in dev
        if settings.ENV == "staging" and "customer" in intent.name:
            return False  # Drop customer notifications in staging
        return True
```

### Pattern 2: Feature Flag Integration

```python
class FeatureFlagPolicy:
    def allows(self, intent):
        feature = intent.dispatch_options.get("feature")
        if feature and not feature_flags.is_enabled(feature):
            return False
        return True

# Usage
airlock.enqueue(
    new_feature_task,
    _dispatch_options={"feature": "new_checkout"}
)
```

### Pattern 3: Conditional Logging

```python
class VerbosePolicy:
    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    def on_enqueue(self, intent):
        if self.verbose:
            logger.debug(f"Enqueued: {intent.name}")

    def allows(self, intent):
        if self.verbose:
            logger.debug(f"Dispatching: {intent.name}")
        return True
```

## Important Constraints

### Cannot Call enqueue() from Policy

```python
class BadPolicy:
    def on_enqueue(self, intent):
        airlock.enqueue(log_task)  # Raises PolicyEnqueueError!
```

This prevents infinite loops. If you need to trigger side effects from a policy, use a custom scope instead.

### Cannot Reorder Intents

Policies are per-intent boolean gates. They can't reorder:

```python
# ❌ Can't do this
def allows(self, intent):
    if intent.priority == "high":
        move_to_front(intent)  # Not possible
    return True
```

For reordering, override `Scope._dispatch_all()`.

