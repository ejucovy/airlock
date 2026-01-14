"""Tests for airlock.configure() functionality."""

import pytest

from airlock import (
    configure,
    reset_configuration,
    get_configuration,
    scope,
    scoped,
    enqueue,
    Scope,
    AllowAll,
    DropAll,
)


# Custom test scope and policy for testing configuration
class CustomScope(Scope):
    """A test scope that tracks whether it was used."""
    instances = []

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        CustomScope.instances.append(self)


class KwargsCapturingScope(Scope):
    """A test scope that captures kwargs for verification."""
    captured_kwargs = []

    def __init__(self, **kwargs):
        KwargsCapturingScope.captured_kwargs.append(dict(kwargs))
        # Remove custom kwargs before passing to parent
        filtered = {k: v for k, v in kwargs.items() if k in ("policy", "executor")}
        super().__init__(**filtered)


class CustomPolicy:
    """A test policy that tracks calls."""
    instances = []

    def __init__(self):
        CustomPolicy.instances.append(self)

    def on_enqueue(self, intent):
        pass

    def allows(self, intent):
        return True


def tracking_executor(intent):
    """A tracking executor that tracks calls."""
    tracking_executor.calls.append(intent)


tracking_executor.calls = []


@pytest.fixture(autouse=True)
def reset_config():
    """Reset configuration before and after each test."""
    reset_configuration()
    CustomScope.instances = []
    CustomPolicy.instances = []
    KwargsCapturingScope.captured_kwargs = []
    tracking_executor.calls = []
    yield
    reset_configuration()
    CustomScope.instances = []
    CustomPolicy.instances = []
    KwargsCapturingScope.captured_kwargs = []
    tracking_executor.calls = []


class TestConfigureBasics:
    """Tests for configure() and related functions."""

    def test_get_configuration_returns_copy(self):
        """Test that get_configuration() returns a copy."""
        config = get_configuration()
        config["scope_cls"] = CustomScope

        # Original should be unaffected
        assert get_configuration()["scope_cls"] is None

    def test_configure_scope_cls(self):
        """Test configuring scope_cls."""
        configure(scope_cls=CustomScope)

        config = get_configuration()
        assert config["scope_cls"] is CustomScope

    def test_configure_policy(self):
        """Test configuring policy."""
        policy = DropAll()
        configure(policy=policy)

        config = get_configuration()
        assert config["policy"] is policy

    def test_configure_executor(self):
        """Test configuring executor."""
        configure(executor=tracking_executor)

        config = get_configuration()
        assert config["executor"] is tracking_executor

    def test_configure_multiple_values(self):
        """Test configuring multiple values at once."""
        policy = DropAll()
        configure(scope_cls=CustomScope, policy=policy, executor=tracking_executor)

        config = get_configuration()
        assert config["scope_cls"] is CustomScope
        assert config["policy"] is policy
        assert config["executor"] is tracking_executor

    def test_configure_scope_kwargs(self):
        """Test configuring scope_kwargs."""
        configure(scope_kwargs={"custom_arg": "value"})

        config = get_configuration()
        assert config["scope_kwargs"] == {"custom_arg": "value"}

    def test_reset_configuration(self):
        """Test that reset_configuration() clears all settings."""
        configure(
            scope_cls=CustomScope,
            policy=DropAll(),
            executor=tracking_executor,
            scope_kwargs={"custom": True},
        )
        reset_configuration()

        config = get_configuration()
        assert config["scope_cls"] is None
        assert config["policy"] is None
        assert config["executor"] is None
        assert config["scope_kwargs"] == {}

    def test_configure_partial_update(self):
        """Test that configure() only updates provided values."""
        policy = DropAll()
        configure(policy=policy)
        configure(executor=tracking_executor)

        config = get_configuration()
        assert config["scope_cls"] is None  # Not set
        assert config["policy"] is policy  # First call
        assert config["executor"] is tracking_executor  # Second call


class CustomScopeUsesConfiguration:
    """Tests for scope() using configured defaults."""

    def test_scope_uses_configured_scope_cls(self):
        """Test that scope() uses configured scope_cls."""
        configure(scope_cls=CustomScope)

        with scope() as s:
            pass

        assert isinstance(s, CustomScope)
        assert len(CustomScope.instances) == 1

    def test_scope_uses_configured_policy(self):
        """Test that scope() uses configured policy."""
        calls = []

        def tracked_task():
            calls.append(1)

        configure(policy=DropAll())

        with scope():
            enqueue(tracked_task)

        # DropAll should have prevented dispatch
        assert len(calls) == 0

    def test_scope_uses_configured_executor(self):
        """Test that scope() uses configured executor."""
        def my_task():
            pass

        configure(executor=tracking_executor)

        with scope():
            enqueue(my_task)

        # Custom executor should have been used
        assert len(tracking_executor.calls) == 1
        assert tracking_executor.calls[0].task is my_task

    def test_scope_explicit_args_override_config(self):
        """Test that explicit args to scope() override configured defaults."""
        configure(scope_cls=CustomScope)

        with scope(_cls=Scope) as s:
            pass

        assert type(s) is Scope  # Explicit override
        assert len(CustomScope.instances) == 0

    def test_scope_explicit_policy_overrides_config(self):
        """Test that explicit policy overrides configured default."""
        calls = []

        def tracked_task():
            calls.append(1)

        configure(policy=DropAll())

        with scope(policy=AllowAll()):
            enqueue(tracked_task)

        # AllowAll should have allowed dispatch despite configured DropAll
        assert len(calls) == 1

    def test_scope_explicit_executor_overrides_config(self):
        """Test that explicit executor overrides configured default."""
        calls = []

        def other_executor(intent):
            calls.append(intent)

        def my_task():
            pass

        configure(executor=tracking_executor)

        with scope(executor=other_executor):
            enqueue(my_task)

        # Explicit executor should have been used
        assert len(calls) == 1
        assert len(tracking_executor.calls) == 0

    def test_scope_with_no_configuration(self):
        """Test that scope() works with no configuration (uses defaults)."""
        calls = []

        def tracked_task():
            calls.append(1)

        # No configure() call
        with scope():
            enqueue(tracked_task)

        # Should use Scope and AllowAll
        assert len(calls) == 1

    def test_scope_uses_configured_scope_kwargs(self):
        """Test that scope() passes configured scope_kwargs to scope class."""
        configure(
            scope_cls=KwargsCapturingScope,
            scope_kwargs={"custom_option": "configured_value"},
        )

        with scope():
            pass

        assert len(KwargsCapturingScope.captured_kwargs) == 1
        assert KwargsCapturingScope.captured_kwargs[0]["custom_option"] == "configured_value"

    def test_scope_explicit_kwargs_override_configured_scope_kwargs(self):
        """Test that explicit kwargs override configured scope_kwargs."""
        configure(
            scope_cls=KwargsCapturingScope,
            scope_kwargs={"option": "configured", "other": "from_config"},
        )

        with scope(option="explicit"):
            pass

        assert len(KwargsCapturingScope.captured_kwargs) == 1
        # Explicit should override configured
        assert KwargsCapturingScope.captured_kwargs[0]["option"] == "explicit"
        # Non-overridden should still be present
        assert KwargsCapturingScope.captured_kwargs[0]["other"] == "from_config"


class CustomScopedUsesConfiguration:
    """Tests for @scoped() decorator using configured defaults."""

    def test_scoped_uses_configured_scope_cls(self):
        """Test that @scoped() uses configured scope_cls."""
        configure(scope_cls=CustomScope)

        @scoped()
        def my_func():
            pass

        my_func()

        assert len(CustomScope.instances) == 1

    def test_scoped_uses_configured_policy(self):
        """Test that @scoped() uses configured policy."""
        calls = []

        def tracked_task():
            calls.append(1)

        configure(policy=DropAll())

        @scoped()
        def my_func():
            enqueue(tracked_task)

        my_func()

        # DropAll should have prevented dispatch
        assert len(calls) == 0

    def test_scoped_uses_configured_executor(self):
        """Test that @scoped() uses configured executor."""
        def my_task():
            pass

        configure(executor=tracking_executor)

        @scoped()
        def my_func():
            enqueue(my_task)

        my_func()

        # Custom executor should have been used
        assert len(tracking_executor.calls) == 1

    def test_scoped_explicit_args_override_config(self):
        """Test that explicit args to @scoped() override configured defaults."""
        calls = []

        def tracked_task():
            calls.append(1)

        configure(policy=DropAll())

        @scoped(policy=AllowAll())
        def my_func():
            enqueue(tracked_task)

        my_func()

        # Explicit AllowAll should have overridden configured DropAll
        assert len(calls) == 1

    def test_scoped_explicit_cls_overrides_config(self):
        """Test that explicit _cls to @scoped() overrides configured default."""
        configure(scope_cls=CustomScope)

        @scoped(_cls=Scope)
        def my_func():
            pass

        my_func()

        # Explicit Scope should have been used, not CustomScope
        assert len(CustomScope.instances) == 0

    def test_scoped_with_no_configuration(self):
        """Test that @scoped() works with no configuration (uses defaults)."""
        calls = []

        def tracked_task():
            calls.append(1)

        # No configure() call
        @scoped()
        def my_func():
            enqueue(tracked_task)

        my_func()

        # Should use Scope and AllowAll
        assert len(calls) == 1


class TestConfigurationIsolation:
    """Tests for configuration isolation between tests."""

    def test_configuration_does_not_leak_a(self):
        """First test in isolation check."""
        # Should start fresh
        config = get_configuration()
        assert config["scope_cls"] is None
        assert config["policy"] is None
        assert config["executor"] is None

        configure(scope_cls=CustomScope)

    def test_configuration_does_not_leak_b(self):
        """Second test in isolation check - should not see changes from first."""
        config = get_configuration()
        assert config["scope_cls"] is None  # Should be reset


class TestFullIntegrationFlow:
    """Integration tests for the full configuration flow."""

    def test_configure_once_use_everywhere(self):
        """Test that configuration applies to all scope/scoped calls."""

        def tracked_task(call_id):
            tracked_task.calls.append(call_id)

        tracked_task.calls = []

        configure(scope_cls=CustomScope, executor=tracking_executor)

        # Direct scope() call
        with scope():
            enqueue(tracked_task, "from_scope")

        # @scoped() decorator
        @scoped()
        def decorated():
            enqueue(tracked_task, "from_scoped")

        decorated()

        # Both should use configured CustomScope
        assert len(CustomScope.instances) == 2

        # Both should use configured executor
        assert len(tracking_executor.calls) == 2
        assert tracking_executor.calls[0].args == ("from_scope",)
        assert tracking_executor.calls[1].args == ("from_scoped",)

    def test_nested_scopes_both_use_config(self):
        """Test that nested scopes both use configuration."""
        configure(scope_cls=CustomScope)

        with scope() as outer:
            with scope() as inner:
                pass

        assert isinstance(outer, CustomScope)
        assert isinstance(inner, CustomScope)
        assert len(CustomScope.instances) == 2
