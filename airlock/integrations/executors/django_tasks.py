"""
Django tasks executor for airlock.

Dispatches tasks via Django 6+'s built-in tasks framework (django.tasks).
Falls back to synchronous execution for plain callables.

Usage:
    from airlock.integrations.executors.django_tasks import django_tasks_executor

    with airlock.scope(executor=django_tasks_executor):
        airlock.enqueue(my_task, arg1, arg2)

Django tasks are defined using the @task decorator:
    from django.tasks import task

    @task
    def my_task(arg1, arg2):
        ...

Dispatch options (priority, run_after, queue_name, backend) are passed through
to the task's .using() method before enqueueing.
"""

from airlock import Intent


def django_tasks_executor(intent: Intent) -> None:
    """
    Execute intent via Django's built-in tasks framework.

    Passes dispatch_options to the task's .using() method for configuration
    of priority, run_after, queue_name, and backend options.
    Falls back to synchronous execution for plain callables.

    Supported dispatch_options:
        - priority: Integer between -100 and 100 (higher = higher priority)
        - run_after: datetime for deferred execution
        - queue_name: Specific queue for task execution
        - backend: Backend name from TASKS configuration
    """
    task = intent.task
    opts = intent.dispatch_options or {}

    # Django tasks have .enqueue() method
    if hasattr(task, "enqueue"):
        # If we have options, use .using() to configure them
        if opts and hasattr(task, "using"):
            task.using(**opts).enqueue(*intent.args, **intent.kwargs)
        else:
            task.enqueue(*intent.args, **intent.kwargs)
    # Plain callable (fallback)
    else:
        task(*intent.args, **intent.kwargs)
