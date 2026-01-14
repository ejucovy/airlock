"""Celery executor for airlock.

Dispatches tasks via Celery's ``.delay()`` or ``.apply_async()`` methods.
Falls back to synchronous execution for plain callables.
"""

from airlock import Intent


def celery_executor(intent: Intent) -> None:
    """Execute intent via Celery task queue.

    Passes ``dispatch_options`` directly to ``apply_async()`` or ignores them
    for ``.delay()``. Falls back to synchronous execution for plain callables.
    """
    task = intent.task
    opts = intent.dispatch_options or {}

    # Prefer apply_async if we have options or if delay() isn't available
    if hasattr(task, "apply_async"):
        task.apply_async(args=intent.args, kwargs=intent.kwargs, **opts)  # noqa: AIR001
    # Fall back to .delay() (can't pass options)
    elif hasattr(task, "delay"):
        task.delay(*intent.args, **intent.kwargs)  # noqa: AIR001
    # Plain callable (fallback)
    else:
        task(*intent.args, **intent.kwargs)
