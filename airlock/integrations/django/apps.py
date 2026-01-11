"""
Django AppConfig for airlock auto-configuration.

When "airlock.integrations.django" is added to INSTALLED_APPS, Django
automatically discovers this AppConfig and calls ready() on startup.

This configures airlock with Django-appropriate defaults:
- DjangoScope as the default scope class (defers dispatch to on_commit)
- Executor and policy from AIRLOCK settings
"""

from django.apps import AppConfig


class AirlockConfig(AppConfig):
    """
    AppConfig that auto-configures airlock for Django.

    Usage:
        # settings.py
        INSTALLED_APPS = [
            ...
            "airlock.integrations.django",
        ]

        # Optional: customize behavior
        AIRLOCK = {
            "POLICY": "airlock.AllowAll",  # Dotted path or class
            "EXECUTOR": "airlock.integrations.executors.celery.celery_executor",
        }

    This automatically calls airlock.configure() with:
    - scope_cls=DjangoScope (defers dispatch to transaction.on_commit)
    - policy from AIRLOCK["POLICY"] setting
    - executor from AIRLOCK["EXECUTOR"] setting

    After this, all airlock.scope() and @airlock.scoped() calls will
    use these defaults unless explicitly overridden.
    """

    name = "airlock.integrations.django"
    label = "airlock_django"
    verbose_name = "Airlock Django Integration"

    def ready(self) -> None:
        """Configure airlock with Django defaults on app startup."""
        import airlock
        from airlock.integrations.django import (
            DjangoScope,
            get_policy,
            get_executor,
        )

        # Configure airlock with Django-appropriate defaults
        airlock.configure(
            scope_cls=DjangoScope,
            policy=get_policy(),
            executor=get_executor(),
        )
