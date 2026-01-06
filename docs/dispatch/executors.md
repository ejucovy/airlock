# Executors

Executors control **how** intents are executed. They are pluggable functions that dispatch intents via different mechanisms.

## Executor Interface

An executor is simply a callable that accepts an `Intent`:

```python
def my_executor(intent: Intent) -> None:
    """Execute an intent somehow."""
    intent.task(*intent.args, **intent.kwargs)
```

## Built-in Executors

### sync_executor (default)

Executes tasks synchronously:

```python
from airlock.integrations.executors.sync import sync_executor

with airlock.scope(executor=sync_executor):
    airlock.enqueue(my_function, arg=123)
# Executes: my_function(arg=123)
```

### celery_executor

Dispatches via Celery's `.delay()` or `.apply_async()`:

```python
from airlock.integrations.executors.celery import celery_executor

with airlock.scope(executor=celery_executor):
    airlock.enqueue(celery_task, arg=123)
    # Dispatches: celery_task.delay(arg=123)

    airlock.enqueue(
        celery_task,
        arg=123,
        _dispatch_options={"countdown": 60}
    )
    # Dispatches: celery_task.apply_async((arg,), {}, countdown=60)
```

Falls back to sync execution for plain functions.

### django_q_executor

Dispatches all tasks via `async_task()`:

```python
from airlock.integrations.executors.django_q import django_q_executor

with airlock.scope(executor=django_q_executor):
    airlock.enqueue(any_function, arg=123)
# Dispatches: async_task(any_function, arg=123)
```

### huey_executor

Dispatches via Huey's `.schedule()`:

```python
from airlock.integrations.executors.huey import huey_executor

with airlock.scope(executor=huey_executor):
    airlock.enqueue(huey_task, arg=123)
# Dispatches: huey_task.schedule((arg,), {})
```

Falls back to sync execution for plain functions.

### dramatiq_executor

Dispatches via Dramatiq's `.send()`:

```python
from airlock.integrations.executors.dramatiq import dramatiq_executor

with airlock.scope(executor=dramatiq_executor):
    airlock.enqueue(dramatiq_actor, arg=123)
# Dispatches: dramatiq_actor.send(arg=123)
```

Falls back to sync execution for plain functions.

## Writing Custom Executors

Create your own executor for custom dispatch logic:

### Thread Pool Executor

```python
from concurrent.futures import ThreadPoolExecutor

executor_pool = ThreadPoolExecutor(max_workers=4)

def thread_executor(intent):
    """Execute in thread pool."""
    executor_pool.submit(intent.task, *intent.args, **intent.kwargs)

with airlock.scope(executor=thread_executor):
    airlock.enqueue(cpu_bound_task)
```

### AWS Lambda Executor

```python
import boto3

lambda_client = boto3.client('lambda')

def lambda_executor(intent):
    """Execute via AWS Lambda."""
    lambda_client.invoke(
        FunctionName=intent.name,
        InvocationType='Event',
        Payload=json.dumps({
            'args': intent.args,
            'kwargs': intent.kwargs,
        })
    )

with airlock.scope(executor=lambda_executor):
    airlock.enqueue(remote_task, data=payload)
```

### Logging Executor

```python
def logging_executor(intent):
    """Log instead of executing (dry-run)."""
    logger.info(f"Would execute: {intent.name}({intent.args}, {intent.kwargs})")

with airlock.scope(executor=logging_executor):
    airlock.enqueue(dangerous_task)  # Just logs, doesn't execute
```

## Executor Selection

### Via Scope Parameter

```python
with airlock.scope(executor=celery_executor):
    # ...
```

### Via Django Settings

```python
# settings.py
AIRLOCK = {
    "TASK_BACKEND": "airlock.integrations.executors.celery.celery_executor",
}
```

### Via Scope Subclass

```python
class CeleryScope(Scope):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('executor', celery_executor)
        super().__init__(*args, **kwargs)

with airlock.scope(_cls=CeleryScope):
    # Uses celery_executor by default
```

## Next Steps

- [Dispatch Options](options.md) - Pass executor-specific options
- [How Dispatch Works](how-it-works.md) - Understanding dispatch flow
