# Django Integration

Django-specific components for airlock.

```python
from airlock.integrations.django import DjangoScope, AirlockMiddleware, airlock_command
```

## Configuration

Configure via `settings.py`:

```python
AIRLOCK = {
    "POLICY": "airlock.AllowAll",  # Dotted path or callable
    "EXECUTOR": "airlock.integrations.executors.celery.celery_executor",
    "SCOPE": "airlock.integrations.django.DjangoScope",
}
```

## Classes

::: airlock.integrations.django.DjangoScope
    options:
      show_root_heading: true
      members:
        - schedule_dispatch

::: airlock.integrations.django.AirlockMiddleware
    options:
      show_root_heading: true
      members:
        - should_flush

## Functions

::: airlock.integrations.django.airlock_command
    options:
      show_root_heading: true

::: airlock.integrations.django.get_executor
    options:
      show_root_heading: true

::: airlock.integrations.django.get_policy
    options:
      show_root_heading: true

::: airlock.integrations.django.get_scope_class
    options:
      show_root_heading: true
