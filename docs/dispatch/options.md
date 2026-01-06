# Dispatch Options

Pass queue-specific options via `_dispatch_options`. Options are passed directly to the underlying dispatch method.

## Usage

### With Celery

```python
# With celery_executor
airlock.enqueue(
    send_email,
    user_id=123,
    _dispatch_options={"countdown": 60, "queue": "emails"},
)
# Calls: task.apply_async(args=(user_id,), kwargs={}, countdown=60, queue="emails")
```

### With django-q

```python
# With django_q_executor
airlock.enqueue(
    send_email,
    user_id=123,
    _dispatch_options={"group": "emails", "timeout": 60},
)
# Calls: async_task(send_email, user_id=123, group="emails", timeout=60)
```

## Executor-Specific Options

Options are specific to your executor:

- Use **Celery options** with `celery_executor`
- Use **django-q options** with `django_q_executor`
- Use **Huey options** with `huey_executor`
- Use **Dramatiq options** with `dramatiq_executor`

For plain callables, `_dispatch_options` is silently ignored.

## Common Options

### Celery

- `countdown`: Delay in seconds
- `eta`: Specific datetime
- `queue`: Queue name
- `priority`: Task priority
- `expires`: Expiration time

[See Celery docs](https://docs.celeryproject.org/en/stable/reference/celery.app.task.html#celery.app.task.Task.apply_async)

### django-q

- `group`: Task group name
- `timeout`: Task timeout in seconds
- `hook`: Post-execution hook
- `retry`: Retry count

[See django-q docs](https://django-q.readthedocs.io/en/latest/tasks.html)

### Huey

- `delay`: Delay in seconds
- `eta`: Specific datetime
- `retries`: Number of retries

[See Huey docs](https://huey.readthedocs.io/en/latest/)

### Dramatiq

- `delay`: Delay in milliseconds
- `max_retries`: Maximum retry count
- `priority`: Message priority

[See Dramatiq docs](https://dramatiq.io/reference.html)

## Next Steps

- [How Dispatch Works](how-it-works.md) - Understanding executors
- [Executors](executors.md) - Detailed executor documentation
