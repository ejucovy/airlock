"""
Flake8 plugin for detecting direct .delay() and .apply_async() calls.

Flags calls that bypass airlock, encouraging use of airlock.enqueue().

Usage:
    flake8 src/

Suppression:
    task.delay(arg)  # noqa: AIR001
"""

import ast
from typing import Iterator

AIR001 = "AIR001 Direct .{method}() call bypasses airlock"


class AirlockChecker:
    """Flake8 checker for airlock bypass detection."""

    name = "airlock"
    version = "0.1.0"

    def __init__(self, tree: ast.AST) -> None:
        self.tree = tree

    def run(self) -> Iterator[tuple[int, int, str, type]]:
        """Yield lint errors for direct .delay() and .apply_async() calls."""
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in ("delay", "apply_async"):
                    yield (
                        node.lineno,
                        node.col_offset,
                        AIR001.format(method=node.func.attr),
                        type(self),
                    )
