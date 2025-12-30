"""
Django integration for airlock.

Provides:
- DjangoScope: Defers dispatch to transaction.on_commit()
- AirlockMiddleware: Wraps requests in a scope
- airlock_command: Decorator for management commands

Settings (in settings.py):
    AIRLOCK = {
        "DEFAULT_POLICY": "airlock.AllowAll",  # Dotted path or callable
        "USE_ON_COMMIT": True,              # Defer dispatch to transaction.on_commit
        "DATABASE_ALIAS": "default",        # Database for on_commit
    }
"""

from functools import wraps
from typing import Any, Callable
from importlib import import_module

from django.conf import settings
from django.db import transaction, DEFAULT_DB_ALIAS

import airlock
from airlock import Scope, Intent, AllowAll, DropAll, _execute


# =============================================================================
# Settings
# =============================================================================

DEFAULTS = {
    "DEFAULT_POLICY": "airlock.AllowAll",
    "USE_ON_COMMIT": True,
    "DATABASE_ALIAS": DEFAULT_DB_ALIAS,
}


def get_setting(name: str) -> Any:
    """Get an airlock setting, falling back to defaults."""
    user_settings = getattr(settings, "AIRLOCK", {})
    return user_settings.get(name, DEFAULTS[name])


def import_string(dotted_path: str) -> Any:
    """Import a class or function from a dotted path."""
    module_path, class_name = dotted_path.rsplit(".", 1)
    module = import_module(module_path)
    return getattr(module, class_name)


def get_default_policy():
    """Get the default policy instance."""
    policy_setting = get_setting("DEFAULT_POLICY")
    if callable(policy_setting):
        return policy_setting()
    if isinstance(policy_setting, str):
        policy_class = import_string(policy_setting)
        return policy_class()
    return policy_setting


# =============================================================================
# DjangoScope
# =============================================================================


class DjangoScope(Scope):
    """
    A Django-specific scope that respects database transactions.

    Defers dispatch to transaction.on_commit() so side effects only
    fire after the transaction commits successfully.
    """

    def __init__(self, *, using: str | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.using = using or get_setting("DATABASE_ALIAS")

    def _dispatch_all(self, intents: list[Intent]) -> None:
        """Dispatch intents, optionally deferring to on_commit."""
        if get_setting("USE_ON_COMMIT"):
            def do_dispatch():
                for intent in intents:
                    _execute(intent)
            transaction.on_commit(do_dispatch, using=self.using)
        else:
            for intent in intents:
                _execute(intent)


# =============================================================================
# Middleware
# =============================================================================


class AirlockMiddleware:
    """
    Django middleware that wraps each request in an airlock scope.

    By default:
    - 1xx/2xx/3xx responses: flush
    - 4xx/5xx responses or exceptions: discard

    Subclass and override should_flush() for custom behavior.
    """

    def __init__(self, get_response: Callable) -> None:
        self.get_response = get_response

    def should_flush(self, request, response) -> bool:
        """Override to customize flush behavior."""
        return response.status_code < 400

    def __call__(self, request):
        policy = get_default_policy()

        # Use imperative API for manual terminal state handling.
        # This allows us to decide flush vs discard based on response status.
        s = DjangoScope(policy=policy)
        s.enter()
        request.airlock_scope = s

        exception = None
        response = None

        try:
            response = self.get_response(request)
        except Exception as e:
            exception = e
        finally:
            # Exit scope first - resets context var so flush/discard is allowed
            s.exit()

        # Terminal state handling (scope no longer active)
        if exception is not None:
            s.discard()
            raise exception

        if self.should_flush(request, response):
            s.flush()
        else:
            s.discard()

        return response


# =============================================================================
# Management command decorator
# =============================================================================


def airlock_command(
    func: Callable = None, *, dry_run_kwarg: str = "dry_run"
) -> Callable:
    """
    Decorator for Django management commands.

    Wraps the handle() method in an airlock scope.
    If options[dry_run_kwarg] is True, uses DropAll policy.

    Transaction semantics:
        Flush occurs at the end of handle(). If USE_ON_COMMIT is True (default),
        dispatch is deferred to transaction.on_commit(). This means:

        - With an active transaction: dispatch occurs after commit
        - Without a transaction: dispatch occurs immediately at end of handle()

        In practice, for most management commands that don't wrap their logic
        in transaction.atomic(), the mental boundary is still "end of handle()".

    Usage:
        class Command(BaseCommand):
            def add_arguments(self, parser):
                parser.add_argument('--dry-run', action='store_true')

            @airlock_command
            def handle(self, *args, **options):
                airlock.enqueue(some_task, ...)
    """

    def decorator(handle_func: Callable) -> Callable:
        @wraps(handle_func)
        def wrapper(self, *args, **options):
            is_dry_run = options.get(dry_run_kwarg, False)
            policy = DropAll() if is_dry_run else get_default_policy()

            with airlock.scope(policy=policy, _cls=DjangoScope):
                return handle_func(self, *args, **options)

        return wrapper

    if func is not None:
        return decorator(func)
    return decorator
