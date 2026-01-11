# Celery Integration

Celery-specific components for airlock.

```python
from airlock.integrations.celery import AirlockTask, LegacyTaskShim, install_global_intercept
```

## Task Base Classes

::: airlock.integrations.celery.AirlockTask
    options:
      show_root_heading: true

::: airlock.integrations.celery.LegacyTaskShim
    options:
      show_root_heading: true

## Global Intercept

::: airlock.integrations.celery.install_global_intercept
    options:
      show_root_heading: true

::: airlock.integrations.celery.uninstall_global_intercept
    options:
      show_root_heading: true
