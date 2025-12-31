"""
django-q executor for airlock.

Dispatches plain callables via django-q's async_task().
"""

from django_q.tasks import async_task

from airlock import Intent


def django_q_executor(intent: Intent) -> None:
    """
    Execute intent via django-q's async_task().

    Passes dispatch_options directly to async_task() as keyword arguments.
    """
    opts = intent.dispatch_options or {}
    async_task(intent.task, *intent.args, **intent.kwargs, **opts)
