# Executors

Executors control **how** intents are dispatched. Pass to `airlock.scope(executor=...)`.

```python
from airlock.integrations.executors.sync import sync_executor
from airlock.integrations.executors.celery import celery_executor
from airlock.integrations.executors.django_q import django_q_executor
from airlock.integrations.executors.django_tasks import django_tasks_executor
from airlock.integrations.executors.huey import huey_executor
from airlock.integrations.executors.dramatiq import dramatiq_executor
```

## sync_executor

::: airlock.integrations.executors.sync.sync_executor
    options:
      show_root_heading: true

## celery_executor

::: airlock.integrations.executors.celery.celery_executor
    options:
      show_root_heading: true

## django_q_executor

::: airlock.integrations.executors.django_q.django_q_executor
    options:
      show_root_heading: true

## django_tasks_executor

::: airlock.integrations.executors.django_tasks.django_tasks_executor
    options:
      show_root_heading: true

## huey_executor

::: airlock.integrations.executors.huey.huey_executor
    options:
      show_root_heading: true

## dramatiq_executor

::: airlock.integrations.executors.dramatiq.dramatiq_executor
    options:
      show_root_heading: true

## Writing Custom Executors

An executor is simply a callable that accepts an `Intent`:

```python
def my_executor(intent: Intent) -> None:
    """Execute an intent."""
    intent.task(*intent.args, **intent.kwargs)
```

See [Custom Executors](../extending/custom-executors.md) for examples.
