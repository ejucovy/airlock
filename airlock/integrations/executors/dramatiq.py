"""Dramatiq executor for airlock.

Dispatches tasks via Dramatiq's ``.send()`` or ``.send_with_options()`` methods.
Falls back to synchronous execution for plain callables.
"""

from airlock import Intent


def dramatiq_executor(intent: Intent) -> None:
    """Execute intent via Dramatiq task queue.

    Passes ``dispatch_options`` directly to ``send_with_options()`` or ignores
    them for ``.send()``. Falls back to synchronous execution for plain callables.
    """
    task = intent.task
    opts = intent.dispatch_options or {}

    # Prefer send_with_options if we have options or if send() isn't available
    if hasattr(task, "send_with_options"):
        task.send_with_options(args=intent.args, kwargs=intent.kwargs, **opts)
    # Fall back to .send() (can't pass options)
    elif hasattr(task, "send"):
        task.send(*intent.args, **intent.kwargs)
    # Plain callable (fallback)
    else:
        task(*intent.args, **intent.kwargs)
