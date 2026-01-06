# Custom Executors

Write custom executors to dispatch intents however you want.

## The Executor Interface

An executor is just a callable that accepts an `Intent`:

```python
def my_executor(intent: Intent) -> None:
    """Execute an intent."""
    intent.task(*intent.args, **intent.kwargs)
```

That's it! No inheritance, no protocol, just a function.

## Example: Thread Pool

```python
from concurrent.futures import ThreadPoolExecutor

executor_pool = ThreadPoolExecutor(max_workers=10)

def thread_executor(intent):
    """Execute in thread pool."""
    executor_pool.submit(intent.task, *intent.args, **intent.kwargs)

# Usage
with airlock.scope(executor=thread_executor):
    airlock.enqueue(cpu_bound_task, data)
# Dispatches in background thread
```

## Example: Process Pool

```python
from multiprocessing import Pool

process_pool = Pool(processes=4)

def process_executor(intent):
    """Execute in process pool."""
    process_pool.apply_async(intent.task, intent.args, intent.kwargs)

with airlock.scope(executor=process_executor):
    airlock.enqueue(heavy_computation, large_data)
```

## Example: AWS Lambda

```python
import boto3
import json

lambda_client = boto3.client('lambda')

def lambda_executor(intent):
    """Execute via AWS Lambda."""
    payload = {
        "function": intent.name,
        "args": intent.args,
        "kwargs": intent.kwargs,
    }

    lambda_client.invoke(
        FunctionName=intent.name,
        InvocationType='Event',
        Payload=json.dumps(payload)
    )

with airlock.scope(executor=lambda_executor):
    airlock.enqueue(remote_task, data=payload)
```

## Example: HTTP API

```python
import requests

def api_executor(intent):
    """Execute via HTTP webhook."""
    endpoint = intent.dispatch_options.get("endpoint", "/default")

    requests.post(
        f"https://api.example.com{endpoint}",
        json={
            "task": intent.name,
            "args": intent.args,
            "kwargs": intent.kwargs,
        }
    )

with airlock.scope(executor=api_executor):
    airlock.enqueue(
        remote_task,
        data,
        _dispatch_options={"endpoint": "/tasks/heavy"}
    )
```

## Example: Dry-Run Logger

```python
def logging_executor(intent):
    """Log instead of executing (dry-run)."""
    logger.info(
        f"Would execute: {intent.name}({intent.args}, {intent.kwargs})"
    )

with airlock.scope(executor=logging_executor):
    airlock.enqueue(dangerous_task)  # Just logs, doesn't execute
```

## Example: Conditional Executor

Route to different backends based on intent:

```python
from airlock.integrations.executors.celery import celery_executor
from airlock.integrations.executors.sync import sync_executor

def smart_executor(intent):
    """Route heavy tasks to Celery, light tasks run sync."""
    if intent.dispatch_options.get("heavy"):
        celery_executor(intent)
    else:
        sync_executor(intent)

with airlock.scope(executor=smart_executor):
    airlock.enqueue(light_task)  # Runs sync
    airlock.enqueue(heavy_task, _dispatch_options={"heavy": True})  # Via Celery
```

## Using Dispatch Options

Executors can read `intent.dispatch_options`:

```python
def priority_executor(intent):
    """Execute high-priority tasks immediately, queue low-priority."""
    priority = intent.dispatch_options.get("priority", 5)

    if priority >= 8:
        # High priority: execute immediately
        intent.task(*intent.args, **intent.kwargs)
    else:
        # Low priority: queue for later
        celery_executor(intent)

# Usage
airlock.enqueue(
    urgent_task,
    _dispatch_options={"priority": 10}
)  # Runs immediately

airlock.enqueue(
    batch_task,
    _dispatch_options={"priority": 3}
)  # Queued
```

## Error Handling

Executor exceptions abort flush:

```python
def careful_executor(intent):
    try:
        intent.task(*intent.args, **intent.kwargs)
    except Exception as e:
        # Log but don't crash flush
        logger.error(f"Failed to execute {intent.name}: {e}")
        # Re-raise to abort flush (or don't to continue)
        raise
```

By default, exceptions propagate and abort flush. This is **fail-fast** behavior.

## Composing Executors

Wrap executors for additional behavior:

```python
def with_retry(executor, retries=3):
    """Wrap executor with retry logic."""
    def retrying_executor(intent):
        for attempt in range(retries):
            try:
                executor(intent)
                return
            except Exception as e:
                if attempt == retries - 1:
                    raise
                logger.warning(f"Retry {attempt + 1}/{retries} for {intent.name}")
    return retrying_executor

# Usage
executor = with_retry(celery_executor, retries=3)

with airlock.scope(executor=executor):
    airlock.enqueue(flaky_task)
```

## Testing Custom Executors

```python
def test_thread_executor():
    executed = []

    def track_executor(intent):
        executed.append(intent.name)

    with airlock.scope(executor=track_executor):
        airlock.enqueue(task_a)
        airlock.enqueue(task_b)

    assert len(executed) == 2
    assert executed == ["task_a", "task_b"]
```

## Built-in Executors

Airlock provides executors for common backends:

```python
from airlock.integrations.executors.sync import sync_executor
from airlock.integrations.executors.celery import celery_executor
from airlock.integrations.executors.django_q import django_q_executor
from airlock.integrations.executors.huey import huey_executor
from airlock.integrations.executors.dramatiq import dramatiq_executor
```

See [Dispatch Guide](../guide/dispatch.md) for details.

## Common Patterns

### Pattern 1: Fallback Executor

```python
def fallback_executor(intent):
    """Try Celery, fall back to sync if unavailable."""
    try:
        celery_executor(intent)
    except Exception:
        logger.warning(f"Celery unavailable, running {intent.name} sync")
        sync_executor(intent)
```

### Pattern 2: Batching Executor

```python
class BatchingExecutor:
    def __init__(self, batch_size=10):
        self.batch_size = batch_size
        self.batch = []

    def __call__(self, intent):
        self.batch.append(intent)
        if len(self.batch) >= self.batch_size:
            self.flush_batch()

    def flush_batch(self):
        # Execute batch
        for intent in self.batch:
            intent.task(*intent.args, **intent.kwargs)
        self.batch.clear()

executor = BatchingExecutor(batch_size=100)
```

### Pattern 3: Rate-Limited Executor

```python
import time

class RateLimitedExecutor:
    def __init__(self, max_per_second=10):
        self.interval = 1.0 / max_per_second
        self.last_execute = 0

    def __call__(self, intent):
        now = time.time()
        elapsed = now - self.last_execute
        if elapsed < self.interval:
            time.sleep(self.interval - elapsed)

        intent.task(*intent.args, **intent.kwargs)
        self.last_execute = time.time()
```

## Next Steps

- [Custom Scopes](custom-scopes.md) - Advanced scope customization
- [Custom Policies](custom-policies.md) - Write custom policies
- [Executor API Reference](../api/executors.md) - Complete executor API
