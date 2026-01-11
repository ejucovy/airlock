# Task Wrapper (AirlockTask)

Deep dive on wrapping Celery tasks with automatic scoping.

## What It Does

`AirlockTask` wraps task execution in a scope:

```python
# Without AirlockTask
def my_task():
    do_work()
    airlock.enqueue(followup)  # NoScopeError!

# With AirlockTask
@app.task(base=AirlockTask)
def my_task():
    do_work()
    airlock.enqueue(followup)  # Buffered
    # Dispatches when task exits
```

## Lifecycle

```
Task starts
    |
Scope created and activated
    |
Task body executes
    |
Task completes (success or error)
    |
Scope exits
    |
Should flush? (default: flush on success, discard on error)
    |
Effects dispatch (if flushed)
```

## Customizing Behavior

### Custom Policy

```python
class MyAirlockTask(AirlockTask):
    def get_policy(self):
        # Log all side effects
        return airlock.LogOnFlush(logger)

@app.task(base=MyAirlockTask)
def my_task():
    ...
```

### Custom Executor

```python
class MyAirlockTask(AirlockTask):
    def get_executor(self):
        # Use django-q for nested tasks
        from airlock.integrations.executors.django_q import django_q_executor
        return django_q_executor

@app.task(base=MyAirlockTask)
def my_task():
    airlock.enqueue(nested_task)  # Dispatches via django-q
```

### Custom Flush Behavior

```python
class AlwaysFlushTask(AirlockTask):
    def should_flush(self, error):
        # Flush even on error (for error notification tasks)
        return True

@app.task(base=AlwaysFlushTask)
def send_error_alert():
    airlock.enqueue(notify_oncall, severity="critical")
    raise Exception("Something broke")
    # Still dispatches notification despite exception
```

## Task Chaining

Tasks can trigger other tasks:

```python
@app.task(base=AirlockTask)
def step_1(data):
    result = process(data)
    airlock.enqueue(step_2, result)
    return result

@app.task(base=AirlockTask)
def step_2(data):
    final = finalize(data)
    airlock.enqueue(step_3, final)
    return final

@app.task(base=AirlockTask)
def step_3(data):
    cleanup(data)
```

Each task has its own scope. Effects dispatch when each task completes.

## Retries

Airlock respects Celery retries:

```python
@app.task(base=AirlockTask, max_retries=3)
def flaky_task(order_id):
    try:
        risky_operation()
        airlock.enqueue(success_notification)
    except Exception as e:
        # Scope discards (task failed)
        raise self.retry(exc=e)
```

**Behavior:**
- On retry: scope discards (error path)
- On final success: scope flushes
- On final failure: scope discards

Effects only dispatch when task ultimately succeeds.

## Testing

Test tasks without running broker:

```python
def test_task_side_effects():
    with airlock.scope(policy=airlock.AssertNoEffects()):
        process_order(123)  # Raises if any side effects

def test_task_effects():
    # Run task body directly (not via .delay())
    with airlock.scope() as s:
        process_order(123)

    # Inspect buffered effects
    assert len(s.intents) == 2
    assert s.intents[0].task.__name__ == "send_email"
```

## AirlockTask vs install_global_intercept

| Feature | AirlockTask | install_global_intercept |
|---------|-------------|--------------------------|
| **Explicit** | Opt-in per task | All tasks affected |
| **Safe** | No monkey-patching | Global side effects |
| **Migration** | Medium effort | Quick but not steady-state |
| **Control** | Per-task customization | Global behavior |

**Recommendation:** Use `AirlockTask` for production. Use `install_global_intercept` for migration only.
