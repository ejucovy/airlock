"""
Pluggable executors for airlock.

Executors are callables that take an Intent and execute it via a specific
dispatch mechanism (synchronous, Celery, django-q, Huey, Dramatiq, etc.).

Available executors:
- sync_executor: Synchronous execution (default)
- celery_executor: Dispatch via Celery .delay() / .apply_async()
- django_q_executor: Dispatch via django-q's async_task()
- huey_executor: Dispatch via Huey's .schedule()
- dramatiq_executor: Dispatch via Dramatiq's .send()

Import the executors you need directly from their modules:
    from airlock.integrations.executors.celery import celery_executor
    from airlock.integrations.executors.django_q import django_q_executor

This ensures that optional dependencies are only required when you actually
use the corresponding executor.
"""

__all__ = []
