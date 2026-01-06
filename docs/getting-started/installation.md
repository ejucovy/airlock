# Installation

Install airlock via pip:

```bash
pip install airlock
```

That's it! No additional configuration is required for basic usage.

## Optional Dependencies

Depending on your task queue system, you may want to install airlock alongside:

- **Celery**: `pip install celery`
- **Django-Q**: `pip install django-q`
- **Huey**: `pip install huey`
- **Dramatiq**: `pip install dramatiq`

These are not required unless you're using the corresponding executor integrations.

## Next Steps

- [Quick Start Guide](quick-start.md) - Learn basic usage
- [Django Integration](../integrations/django.md) - Set up Django middleware
- [Celery Integration](../integrations/celery.md) - Configure Celery tasks
