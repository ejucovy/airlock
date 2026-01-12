"""Synchronous executor for airlock.

This is the default executor that simply calls tasks synchronously.
"""

from airlock import Intent


def sync_executor(intent: Intent) -> None:
    """Execute intent synchronously by calling the task directly.

    This is the simplest executor - no queue, no threading, just immediate
    execution. Dispatch options are ignored.
    """
    intent.task(*intent.args, **intent.kwargs)
