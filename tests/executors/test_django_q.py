"""Tests for django_q_executor."""

import pytest
from unittest.mock import Mock, patch

pytest.importorskip("django_q")

from airlock import Intent


def make_intent(task, args=(), kwargs=None, dispatch_options=None):
    return Intent(
        task=task,
        args=args,
        kwargs=kwargs or {},
        dispatch_options=dispatch_options,
    )


def test_django_q_executor_basic():
    """Test django_q_executor calls async_task."""
    from airlock.integrations.executors.django_q import django_q_executor

    with patch("airlock.integrations.executors.django_q.async_task") as mock_async_task:
        mock_task = Mock(__name__="my_task")
        intent = make_intent(mock_task, args=(1, 2), kwargs={"x": 3})

        django_q_executor(intent)

        mock_async_task.assert_called_once_with(mock_task, 1, 2, x=3)


def test_django_q_executor_with_dispatch_options():
    """Test django_q_executor passes dispatch_options to async_task."""
    from airlock.integrations.executors.django_q import django_q_executor

    with patch("airlock.integrations.executors.django_q.async_task") as mock_async_task:
        mock_task = Mock(__name__="my_task")
        intent = make_intent(
            mock_task,
            args=(1,),
            kwargs={"y": 2},
            dispatch_options={"group": "emails", "timeout": 60, "hook": "my_hook"}
        )

        django_q_executor(intent)

        mock_async_task.assert_called_once_with(
            mock_task,
            1,
            y=2,
            group="emails",
            timeout=60,
            hook="my_hook"
        )


def test_django_q_executor_no_args():
    """Test django_q_executor with no arguments."""
    from airlock.integrations.executors.django_q import django_q_executor

    with patch("airlock.integrations.executors.django_q.async_task") as mock_async_task:
        mock_task = Mock(__name__="my_task")
        intent = make_intent(mock_task)

        django_q_executor(intent)

        mock_async_task.assert_called_once_with(mock_task)


def test_django_q_executor_no_dispatch_options():
    """Test django_q_executor works without dispatch_options."""
    from airlock.integrations.executors.django_q import django_q_executor

    with patch("airlock.integrations.executors.django_q.async_task") as mock_async_task:
        mock_task = Mock(__name__="my_task")
        intent = make_intent(mock_task, args=(1,), dispatch_options=None)

        django_q_executor(intent)

        mock_async_task.assert_called_once_with(mock_task, 1)


def test_django_q_executor_implements_protocol():
    """Test django_q_executor implements the Executor protocol."""
    from airlock import Executor
    from airlock.integrations.executors.django_q import django_q_executor

    assert isinstance(django_q_executor, Executor)
