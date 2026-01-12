"""Huey executor for airlock.

Dispatches tasks via Huey's ``.schedule()`` method.
Falls back to synchronous execution for plain callables.
"""

from airlock import Intent


def huey_executor(intent: Intent) -> None:
    """Execute intent via Huey task queue.

    Passes ``dispatch_options`` directly to ``schedule()`` as keyword arguments.
    Falls back to synchronous execution for plain callables.
    """
    task = intent.task
    opts = intent.dispatch_options or {}

    # Huey tasks have .schedule() method
    if hasattr(task, "schedule"):
        task.schedule(args=intent.args, kwargs=intent.kwargs, **opts)
    # Plain callable (fallback)
    else:
        task(*intent.args, **intent.kwargs)
