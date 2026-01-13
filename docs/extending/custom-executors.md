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

with airlock.scope(executor=thread_executor):
    airlock.enqueue(cpu_bound_task, data)
# Dispatches in background thread
```

## Using Dispatch Options

Executors can read `intent.dispatch_options` to customize behavior:

```python
def priority_executor(intent):
    """Execute high-priority tasks immediately, queue low-priority."""
    priority = intent.dispatch_options.get("priority", 5)

    if priority >= 8:
        intent.task(*intent.args, **intent.kwargs)
    else:
        celery_executor(intent)

airlock.enqueue(urgent_task, _dispatch_options={"priority": 10})
```

## Error Handling

Executor exceptions abort flush by default (fail-fast behavior):

```python
def careful_executor(intent):
    try:
        intent.task(*intent.args, **intent.kwargs)
    except Exception as e:
        logger.error(f"Failed to execute {intent.name}: {e}")
        raise  # Re-raise to abort flush, or omit to continue
```

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
                logger.warning(f"Retry {attempt + 1}/{retries}")
    return retrying_executor

executor = with_retry(celery_executor, retries=3)
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

See the [API Reference](../api/executors.md) for details on each executor's behavior.
