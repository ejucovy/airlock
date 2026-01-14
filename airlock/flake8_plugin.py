"""Flake8 plugin for airlock code quality checks.

Checks:
- AIR001: Direct .delay() or .apply_async() calls bypass airlock
- AIR002: Inline import inside function (bad habit)

This plugin is not automatically registered when you install airlock.
To use it, copy this code into your own flake8 plugin. If you'd find a
separate ``flake8-airlock`` package useful, open an issue and let us know!

Suppression::

    task.delay(arg)  # noqa: AIR001
    import foo  # noqa: AIR002
"""

import ast
from pathlib import Path
from typing import Iterator

AIR001 = "AIR001 Direct .{method}() call bypasses airlock"
AIR002 = "AIR002 Inline import inside function"


class AirlockChecker:
    """Flake8 checker for airlock code quality."""

    name = "airlock"
    version = "0.1.0"

    def __init__(self, tree: ast.AST, filename: str = "") -> None:
        self.tree = tree
        self.filename = filename

    def run(self) -> Iterator[tuple[int, int, str, type]]:
        """Yield lint errors."""
        yield from self._check_bypass_calls()
        yield from self._check_inline_imports()

    def _check_bypass_calls(self) -> Iterator[tuple[int, int, str, type]]:
        """Check for direct .delay() and .apply_async() calls."""
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in ("delay", "apply_async"):
                    yield (
                        node.lineno,
                        node.col_offset,
                        AIR001.format(method=node.func.attr),
                        type(self),
                    )

    def _check_inline_imports(self) -> Iterator[tuple[int, int, str, type]]:
        """Check for import statements inside functions."""
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for child in ast.walk(node):
                    if isinstance(child, (ast.Import, ast.ImportFrom)):
                        yield (
                            child.lineno,
                            child.col_offset,
                            AIR002,
                            type(self),
                        )


def check_file(filepath: Path, source: str | None = None) -> list[tuple[str, int, int, str]]:
    """Check a single file for violations. Returns list of (file, line, col, message)."""
    if source is None:
        source = filepath.read_text()

    lines = source.splitlines()
    tree = ast.parse(source)
    checker = AirlockChecker(tree, str(filepath))

    violations = []
    for lineno, col, msg, _ in checker.run():
        # Check for noqa
        line = lines[lineno - 1] if lineno <= len(lines) else ""
        if "# noqa" not in line.lower():
            violations.append((str(filepath), lineno, col, msg))

    return violations


def main() -> int:
    """Run checks on airlock source code. Returns exit code."""
    airlock_dir = Path(__file__).parent

    all_violations = []
    for pyfile in airlock_dir.rglob("*.py"):
        violations = check_file(pyfile)
        all_violations.extend(violations)

    if all_violations:
        for filepath, lineno, col, msg in all_violations:
            print(f"{filepath}:{lineno}:{col}: {msg}")
        return 1

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
