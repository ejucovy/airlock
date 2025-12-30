import pytest
from unittest.mock import MagicMock, patch

import airlock
from airlock import Intent, AllowAll, ScopeStateError


# Configure Django settings before importing Django-dependent code
from django.conf import settings
if not settings.configured:
    settings.configure(
        DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3"}},
        INSTALLED_APPS=["django.contrib.contenttypes"],
    )

from airlock.integrations.django import DjangoScope, AirlockMiddleware


def dummy_task():
    pass


@pytest.fixture
def mock_transaction():
    with patch("airlock.integrations.django.transaction") as m:
        yield m


def test_django_scope_flush_calls_on_commit(mock_transaction):
    """Test that DjangoScope registers flush with on_commit."""
    s = DjangoScope(policy=AllowAll())
    s._add(Intent(task=dummy_task, args=(), kwargs={}))

    s.flush()

    # Scope should be marked as flushed immediately
    assert s._flushed is True
    # on_commit should have been called
    mock_transaction.on_commit.assert_called_once()


def test_django_scope_flush_double_flush_raises():
    """Test that flushing twice raises ScopeStateError."""
    s = DjangoScope(policy=AllowAll())
    with patch("airlock.integrations.django.transaction"):
        s.flush()
        with pytest.raises(ScopeStateError, match="already been flushed"):
            s.flush()


# =============================================================================
# Real middleware integration tests (no mocking of airlock.scope)
# =============================================================================


def test_middleware_real_flush_on_success(mock_transaction):
    """Test middleware with real scope - flushes on 200 OK."""
    get_response = MagicMock()
    get_response.return_value.status_code = 200

    middleware = AirlockMiddleware(get_response)
    request = MagicMock()

    # This should work without raising
    response = middleware(request)

    assert response.status_code == 200


def test_middleware_real_discard_on_error(mock_transaction):
    """Test middleware with real scope - discards on 500 Error."""
    get_response = MagicMock()
    get_response.return_value.status_code = 500

    middleware = AirlockMiddleware(get_response)
    request = MagicMock()

    # This should work without raising
    response = middleware(request)

    assert response.status_code == 500


def test_middleware_real_discard_on_exception(mock_transaction):
    """Test middleware with real scope - discards on exception."""
    get_response = MagicMock()
    get_response.side_effect = ValueError("boom")

    middleware = AirlockMiddleware(get_response)
    request = MagicMock()

    # This should discard and re-raise, not raise ScopeStateError
    with pytest.raises(ValueError, match="boom"):
        middleware(request)


# =============================================================================
# Mock-based tests (for verifying flush/discard is called)
# =============================================================================


def test_middleware_flushes_on_success():
    """Test that middleware flushes on 200 OK."""
    get_response = MagicMock()
    get_response.return_value.status_code = 200

    middleware = AirlockMiddleware(get_response)
    request = MagicMock()

    with patch("airlock.integrations.django.airlock.scope") as mock_scope_cm:
        mock_s = MagicMock()
        mock_scope_cm.return_value.__enter__.return_value = mock_s

        middleware(request)

        mock_s.flush.assert_called_once()
        mock_s.discard.assert_not_called()


def test_middleware_discards_on_error():
    """Test that middleware discards on 500 Error."""
    get_response = MagicMock()
    get_response.return_value.status_code = 500

    middleware = AirlockMiddleware(get_response)
    request = MagicMock()

    with patch("airlock.integrations.django.airlock.scope") as mock_scope_cm:
        mock_s = MagicMock()
        mock_scope_cm.return_value.__enter__.return_value = mock_s

        middleware(request)

        mock_s.flush.assert_not_called()
        mock_s.discard.assert_called_once()


def test_middleware_discards_on_exception():
    """Test that middleware discards on exception."""
    get_response = MagicMock()
    get_response.side_effect = ValueError("boom")

    middleware = AirlockMiddleware(get_response)
    request = MagicMock()

    with patch("airlock.integrations.django.airlock.scope") as mock_scope_cm:
        mock_s = MagicMock()
        mock_scope_cm.return_value.__enter__.return_value = mock_s

        with pytest.raises(ValueError):
            middleware(request)

        mock_s.flush.assert_not_called()
        mock_s.discard.assert_called_once()
