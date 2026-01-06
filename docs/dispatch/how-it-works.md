# How Dispatch Works

Dispatch is handled by **executors** — pluggable functions that execute intents. The default executor runs tasks synchronously.

## Built-in Executors

```python
from airlock.integrations.executors.sync import sync_executor          # Default: task(*args, **kwargs)
from airlock.integrations.executors.celery import celery_executor      # Celery: task.delay() or task.apply_async()
from airlock.integrations.executors.django_q import django_q_executor  # django-q: async_task(task, *args, **kwargs)
from airlock.integrations.executors.huey import huey_executor          # Huey: task.schedule()
from airlock.integrations.executors.dramatiq import dramatiq_executor  # Dramatiq: task.send() or task.send_with_options()
```

## Executor Behavior

### Celery Executor

Checks for `.delay()` / `.apply_async()` and falls back to sync:

```python
with airlock.scope(executor=celery_executor):
    airlock.enqueue(celery_task, ...)    # Dispatches via .delay()
    airlock.enqueue(plain_function, ...) # Falls back to sync
```

### django-q Executor

Always uses `async_task()`:

```python
with airlock.scope(executor=django_q_executor):
    airlock.enqueue(any_function, ...)  # All go via async_task()
```

### Huey Executor

Checks for `.schedule()`:

```python
with airlock.scope(executor=huey_executor):
    airlock.enqueue(huey_task, ...)      # Dispatches via .schedule()
    airlock.enqueue(plain_function, ...) # Falls back to sync
```

### Dramatiq Executor

Checks for `.send()`:

```python
with airlock.scope(executor=dramatiq_executor):
    airlock.enqueue(dramatiq_actor, ...)  # Dispatches via .send()
    airlock.enqueue(plain_function, ...)  # Falls back to sync
```

## Dependencies

Each executor requires its corresponding task queue library to be installed. Import the executor only if you have the library available:

- `celery_executor` requires `celery`
- `django_q_executor` requires `django-q`
- `huey_executor` requires `huey`
- `dramatiq_executor` requires `dramatiq`

## Executor Composition

Executors are **composable** — use different executors with different scopes, or write your own for custom dispatch mechanisms.

```python
# Use different executors for different contexts
with airlock.scope(executor=celery_executor):
    airlock.enqueue(background_task)

with airlock.scope(executor=sync_executor):
    airlock.enqueue(immediate_task)
```

## Custom Executors

Write your own executor for custom dispatch:

```python
def my_executor(intent):
    """Custom executor that logs before executing."""
    logger.info(f"Executing: {intent.name}")
    intent.task(*intent.args, **intent.kwargs)

with airlock.scope(executor=my_executor):
    airlock.enqueue(my_task)
```

An executor is just a callable that accepts an `Intent` and executes it however you want.

## Next Steps

- [Dispatch Options](options.md) - Pass queue-specific options
- [Executors](executors.md) - Detailed executor documentation
