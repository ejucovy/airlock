"""Tests for context handling."""

import pytest

from airlock import get_current_scope, _current_scope, _in_policy


class TestContextVarHandling:
    """Tests for the ContextVar locator system."""

    def test_no_scope_by_default(self):
        """Test that no scope is active by default."""
        assert get_current_scope() is None

    def test_set_and_get_scope(self):
        """Test setting and getting a scope."""

        class MockScope:
            pass

        scope = MockScope()
        token = _current_scope.set(scope)

        try:
            assert get_current_scope() is scope
        finally:
            _current_scope.reset(token)

    def test_reset_restores_previous(self):
        """Test that reset restores the previous value."""
        assert get_current_scope() is None

        class MockScope:
            pass

        scope = MockScope()
        token = _current_scope.set(scope)
        _current_scope.reset(token)

        assert get_current_scope() is None

    def test_nested_scopes(self):
        """Test nested scope handling."""

        class MockScope:
            def __init__(self, name):
                self.name = name

        outer = MockScope("outer")
        inner = MockScope("inner")

        token_outer = _current_scope.set(outer)
        assert get_current_scope().name == "outer"

        token_inner = _current_scope.set(inner)
        assert get_current_scope().name == "inner"

        _current_scope.reset(token_inner)
        assert get_current_scope().name == "outer"

        _current_scope.reset(token_outer)
        assert get_current_scope() is None


class TestInPolicyFlag:
    """Tests for the in-policy flag."""

    def test_not_in_policy_by_default(self):
        """Test that we're not in a policy by default."""
        assert _in_policy.get() is False

    def test_set_in_policy(self):
        """Test setting the in-policy flag."""
        token = _in_policy.set(True)

        try:
            assert _in_policy.get() is True
        finally:
            _in_policy.reset(token)

        assert _in_policy.get() is False

    def test_nested_policy_calls(self):
        """Test nested policy flag handling."""
        assert _in_policy.get() is False

        token1 = _in_policy.set(True)
        assert _in_policy.get() is True

        token2 = _in_policy.set(True)
        assert _in_policy.get() is True

        _in_policy.reset(token2)
        assert _in_policy.get() is True

        _in_policy.reset(token1)
        assert _in_policy.get() is False
