# Dispatch Guide

How side effects are executed: executors, options, and dispatch flow.

## The Dispatch Pipeline

```
airlock.enqueue(task, ...)
    ↓
Buffer intent
    ↓
[Scope exits]
    ↓
Apply policies (filter)
    ↓
Execute via executor
    ↓
task(*args, **kwargs)
```

## Executors

Executors control **how** intents execute.

### sync_executor (Default)

```python
from airlock.integrations.executors.sync import sync_executor

with airlock.scope(executor=sync_executor):
    airlock.enqueue(my_function, arg=123)
# Executes: my_function(arg=123)
```

Runs synchronously at flush time.

### celery_executor

```python
from airlock.integrations.executors.celery import celery_executor

with airlock.scope(executor=celery_executor):
    airlock.enqueue(celery_task, arg=123)
    # Dispatches: celery_task.delay(arg=123)

    airlock.enqueue(plain_function, arg=123)
    # Falls back to sync: plain_function(arg=123)
```

Checks for `.delay()` / `.apply_async()`, falls back to sync.

### django_q_executor

```python
from airlock.integrations.executors.django_q import django_q_executor

with airlock.scope(executor=django_q_executor):
    airlock.enqueue(any_function, arg=123)
# Dispatches: async_task(any_function, arg=123)
```

Always uses `async_task()` for all callables.

### huey_executor

```python
from airlock.integrations.executors.huey import huey_executor

with airlock.scope(executor=huey_executor):
    airlock.enqueue(huey_task, arg=123)
    # Dispatches: huey_task.schedule(args=(arg,), kwargs={})
```

Checks for `.schedule()`, falls back to sync.

### dramatiq_executor

```python
from airlock.integrations.executors.dramatiq import dramatiq_executor

with airlock.scope(executor=dramatiq_executor):
    airlock.enqueue(dramatiq_actor, arg=123)
    # Dispatches: dramatiq_actor.send(arg=123)
```

Checks for `.send()`, falls back to sync.

## Dispatch Options

Pass queue-specific options via `_dispatch_options`:

```python
airlock.enqueue(
    send_email,
    user_id=123,
    _dispatch_options={
        "countdown": 60,      # Delay 60 seconds
        "queue": "emails",    # Use specific queue
        "priority": 9,        # High priority
    }
)
```

### Celery Options

With `celery_executor`:

```python
airlock.enqueue(
    task,
    arg,
    _dispatch_options={
        "countdown": 60,           # Delay in seconds
        "eta": datetime(...),      # Specific datetime
        "queue": "high-priority",  # Queue name
        "priority": 9,             # 0-9 (0=lowest, 9=highest)
        "expires": 3600,           # Expire after 1 hour
        "retry": True,             # Enable retries
        "retry_policy": {...},     # Retry configuration
    }
)
```

[Celery docs →](https://docs.celeryproject.org/en/stable/reference/celery.app.task.html#celery.app.task.Task.apply_async)

### django-q Options

With `django_q_executor`:

```python
airlock.enqueue(
    task,
    arg,
    _dispatch_options={
        "group": "batch-jobs",     # Task group
        "timeout": 300,            # Timeout in seconds
        "hook": "my_hook",         # Post-execution hook
        "retry": 3,                # Retry count
        "sync": False,             # Run async
    }
)
```

[django-q docs →](https://django-q.readthedocs.io/en/latest/tasks.html)

### Huey Options

With `huey_executor`:

```python
airlock.enqueue(
    task,
    arg,
    _dispatch_options={
        "delay": 60,              # Delay in seconds
        "eta": datetime(...),     # Specific datetime
        "retries": 3,             # Number of retries
    }
)
```

[Huey docs →](https://huey.readthedocs.io/en/latest/)

### Dramatiq Options

With `dramatiq_executor`:

```python
airlock.enqueue(
    actor,
    arg,
    _dispatch_options={
        "delay": 60000,           # Delay in milliseconds
        "max_retries": 3,         # Retry limit
        "priority": 10,           # Message priority
    }
)
```

[Dramatiq docs →](https://dramatiq.io/reference.html)

## Configuring Default Executor

### Via Django Settings

```python
# settings.py
AIRLOCK = {
    "TASK_BACKEND": "airlock.integrations.executors.celery.celery_executor",
}
```

Now all `DjangoScope` instances use Celery by default.

### Via Custom Scope

```python
from airlock.integrations.executors.celery import celery_executor

class CeleryScope(Scope):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('executor', celery_executor)
        super().__init__(*args, **kwargs)

with airlock.scope(_cls=CeleryScope):
    airlock.enqueue(task)  # Uses Celery
```

## Dispatch Flow

### 1. Enqueue Phase

```python
with airlock.scope() as s:
    airlock.enqueue(task_a)
    airlock.enqueue(task_b)
    # Intents buffered in memory
```

### 2. Policy Phase (at flush)

```python
# Scope applies policy to each intent
for intent in intents:
    # Check local policies
    if not intent.passes_local_policies():
        continue  # Drop

    # Check scope policy
    if not scope.policy.allows(intent):
        continue  # Drop

    # Intent allowed
    allowed_intents.append(intent)
```

### 3. Dispatch Phase

```python
# Scope calls _dispatch_all()
for intent in allowed_intents:
    executor(intent)  # Execute via configured executor
```

## Error Handling

### Dispatch Errors are Fail-Fast

If an executor raises during dispatch, flush aborts:

```python
with airlock.scope():
    airlock.enqueue(task_a)  # Will execute
    airlock.enqueue(task_b)  # Raises (broker down)
    airlock.enqueue(task_c)  # Never attempted

# task_a: ✅ dispatched
# task_b: ❌ raised exception
# task_c: ⚠️  never dispatched (flush aborted)
```

This is intentional - infrastructure failures should fail loudly.

### For Async Executors

With Celery/django-q/etc., "dispatch" means "submit to queue", not "run the task":

```python
with airlock.scope(executor=celery_executor):
    airlock.enqueue(task)
# If broker is available: succeeds (task queued)
# If broker is down: raises (flush aborts)
```

Task execution happens asynchronously. Failures are handled by the task queue, not airlock.

## Custom Executors

Write your own for custom dispatch:

```python
def my_executor(intent):
    """Execute via custom mechanism."""
    logger.info(f"Executing: {intent.name}")
    intent.task(*intent.args, **intent.kwargs)

with airlock.scope(executor=my_executor):
    airlock.enqueue(task)
```

See [Custom Executors Guide](../extending/custom-executors.md) for examples.

## Common Patterns

### Pattern 1: Conditional Executor

```python
def smart_executor(intent):
    """Route to different backends based on intent."""
    if intent.dispatch_options.get("heavy"):
        celery_executor(intent)
    else:
        sync_executor(intent)

with airlock.scope(executor=smart_executor):
    airlock.enqueue(light_task)                            # Sync
    airlock.enqueue(heavy_task, _dispatch_options={"heavy": True})  # Celery
```

### Pattern 2: Fallback Executor

```python
def fallback_executor(intent):
    """Try Celery, fall back to sync if unavailable."""
    try:
        celery_executor(intent)
    except Exception:
        logger.warning(f"Celery unavailable, running {intent.name} sync")
        sync_executor(intent)
```

### Pattern 3: Batching Executor

```python
class BatchingExecutor:
    def __init__(self, batch_size=10):
        self.batch = []
        self.batch_size = batch_size

    def __call__(self, intent):
        self.batch.append(intent)
        if len(self.batch) >= self.batch_size:
            self.flush()

    def flush(self):
        # Execute batch
        for intent in self.batch:
            intent.task(*intent.args, **intent.kwargs)
        self.batch.clear()
```

## Next Steps

- [Custom Executors](../extending/custom-executors.md) - Write your own
- [Executors API](../api/executors.md) - Complete executor reference (if exists)
- [Policies Guide](policies.md) - Filter what executes
