"""Tests for Intent."""

import pytest

from airlock import Intent, AllowAll, DropAll


def dummy_task():
    """A dummy task for testing."""
    pass


def another_task():
    """Another dummy task."""
    pass


class TestIntent:
    """Tests for the Intent dataclass."""

    def test_create_basic_intent(self):
        """Test creating a basic intent with just a task."""
        intent = Intent(task=dummy_task, args=(), kwargs={})

        assert intent.task is dummy_task
        assert intent.args == ()
        assert intent.kwargs == {}
        assert intent.origin is None

    def test_create_intent_with_args(self):
        """Test creating an intent with positional arguments."""
        intent = Intent(task=dummy_task, args=(1, 2, 3), kwargs={})

        assert intent.args == (1, 2, 3)

    def test_create_intent_with_kwargs(self):
        """Test creating an intent with keyword arguments."""
        intent = Intent(
            task=dummy_task,
            args=(),
            kwargs={"user_id": 123, "action": "create"},
        )

        assert intent.kwargs == {"user_id": 123, "action": "create"}

    def test_create_intent_with_origin(self):
        """Test creating an intent with an origin."""
        intent = Intent(
            task=dummy_task,
            args=(),
            kwargs={},
            origin="mymodule:myfunction",
        )

        assert intent.origin == "mymodule:myfunction"

    def test_intent_is_frozen(self):
        """Test that intents are immutable."""
        intent = Intent(task=dummy_task, args=(), kwargs={})

        with pytest.raises(AttributeError):
            intent.task = another_task

    def test_intent_is_not_hashable(self):
        """Test that intents are not hashable (kwargs may contain unhashable values)."""
        intent = Intent(task=dummy_task, args=(1,), kwargs={"a": 1})

        with pytest.raises(TypeError, match="unhashable"):
            hash(intent)

    def test_intent_name_derived_from_function(self):
        """Test that name is derived from the task callable."""
        intent = Intent(task=dummy_task, args=(), kwargs={})

        # Name should include module and function name
        assert "dummy_task" in intent.name

    def test_intent_name_from_celery_like_task(self):
        """Test that name uses .name attribute if available."""

        class FakeCeleryTask:
            name = "myapp.tasks.send_email"

            def __call__(self):
                pass

        task = FakeCeleryTask()
        intent = Intent(task=task, args=(), kwargs={})

        assert intent.name == "myapp.tasks.send_email"

    def test_intent_repr(self):
        """Test intent string representation."""
        intent = Intent(
            task=dummy_task,
            args=(123,),
            kwargs={"urgent": True},
            origin="models:save",
        )

        repr_str = repr(intent)
        assert "dummy_task" in repr_str
        assert "(123,)" in repr_str
        assert "urgent" in repr_str
        assert "models:save" in repr_str

    def test_args_converted_to_tuple(self):
        """Test that list args are converted to tuple."""
        intent = Intent(task=dummy_task, args=[1, 2, 3], kwargs={})

        assert isinstance(intent.args, tuple)
        assert intent.args == (1, 2, 3)

    def test_create_intent_with_dispatch_options(self):
        """Test creating an intent with dispatch options."""
        intent = Intent(
            task=dummy_task,
            args=(),
            kwargs={},
            dispatch_options={"countdown": 60, "queue": "emails"},
        )

        assert intent.dispatch_options == {"countdown": 60, "queue": "emails"}

    def test_dispatch_options_default_none(self):
        """Test that dispatch_options defaults to None."""
        intent = Intent(task=dummy_task, args=(), kwargs={})

        assert intent.dispatch_options is None

    def test_intent_repr_with_dispatch_options(self):
        """Test intent string representation includes dispatch_options."""
        intent = Intent(
            task=dummy_task,
            args=(),
            kwargs={},
            dispatch_options={"countdown": 30},
        )

        repr_str = repr(intent)
        assert "dispatch_options" in repr_str
        assert "countdown" in repr_str


class TestPassesLocalPolicies:
    """Tests for Intent.passes_local_policies()."""

    def test_passes_with_no_local_policies(self):
        """Test passes_local_policies returns True when no local policies."""
        intent = Intent(task=dummy_task, args=(), kwargs={})

        # No local policies - should pass (empty loop)
        assert intent.passes_local_policies() is True

    def test_passes_with_allowing_policy(self):
        """Test passes_local_policies with policy that allows."""

        intent = Intent(
            task=dummy_task,
            args=(),
            kwargs={},
            _local_policies=(AllowAll(),),
        )

        assert intent.passes_local_policies() is True

    def test_fails_with_blocking_policy(self):
        """Test passes_local_policies with policy that blocks."""

        intent = Intent(
            task=dummy_task,
            args=(),
            kwargs={},
            _local_policies=(DropAll(),),
        )

        assert intent.passes_local_policies() is False

