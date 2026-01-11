"""Tests for the flake8 plugin."""

import ast

from airlock.flake8_plugin import AirlockChecker


def check(code: str) -> list[tuple[int, int, str]]:
    """Run the checker on code and return errors (without type)."""
    tree = ast.parse(code)
    checker = AirlockChecker(tree)
    return [(line, col, msg) for line, col, msg, _ in checker.run()]


class TestAirlockChecker:
    def test_detects_delay(self):
        errors = check("task.delay(1, 2)")
        assert len(errors) == 1
        assert errors[0][0] == 1  # line
        assert "delay" in errors[0][2]

    def test_detects_apply_async(self):
        errors = check("task.apply_async(args=(1,))")
        assert len(errors) == 1
        assert "apply_async" in errors[0][2]

    def test_ignores_other_methods(self):
        errors = check("task.run(1, 2)")
        assert len(errors) == 0

    def test_ignores_plain_calls(self):
        errors = check("delay(1, 2)")
        assert len(errors) == 0

    def test_multiple_violations(self):
        code = """
task1.delay(1)
task2.apply_async(args=(2,))
task3.delay(3)
"""
        errors = check(code)
        assert len(errors) == 3

    def test_nested_call(self):
        errors = check("foo(task.delay(1))")
        assert len(errors) == 1

    def test_error_code_format(self):
        errors = check("task.delay()")
        assert errors[0][2] == "AIR001 Direct .delay() call bypasses airlock"
