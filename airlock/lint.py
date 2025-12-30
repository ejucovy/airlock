"""
Linter for detecting direct .delay() and .apply_async() calls.

Flags calls that bypass airlock, encouraging use of airlock.enqueue().

Usage:
    python -m airlock.lint src/
    python -m airlock.lint --fix src/  # (future: auto-fix)

Suppression:
    task.delay(arg)  # noqa: airlock
"""

import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


@dataclass
class Violation:
    """A detected bypass of airlock."""

    path: Path
    line: int
    col: int
    method: str  # "delay" or "apply_async"
    source_line: str

    def __str__(self) -> str:
        return (
            f"{self.path}:{self.line}:{self.col}: "
            f"AIR001 Direct .{self.method}() call bypasses airlock"
        )


class DelayCallVisitor(ast.NodeVisitor):
    """AST visitor that finds .delay() and .apply_async() calls."""

    def __init__(self, source_lines: list[str]) -> None:
        self.source_lines = source_lines
        self.violations: list[tuple[int, int, str]] = []

    def visit_Call(self, node: ast.Call) -> None:
        # Look for something.delay(...) or something.apply_async(...)
        if isinstance(node.func, ast.Attribute):
            if node.func.attr in ("delay", "apply_async"):
                line_idx = node.lineno - 1
                if line_idx < len(self.source_lines):
                    source_line = self.source_lines[line_idx]
                    # Check for noqa comment
                    if not _has_noqa(source_line):
                        self.violations.append(
                            (node.lineno, node.col_offset, node.func.attr)
                        )
        self.generic_visit(node)


def _has_noqa(line: str) -> bool:
    """Check if line has a noqa: airlock comment."""
    line_lower = line.lower()
    if "# noqa: airlock" in line_lower:
        return True
    if "# noqa:airlock" in line_lower:
        return True
    # Also accept generic noqa
    if "# noqa" in line_lower and "airlock" in line_lower:
        return True
    return False


def check_file(path: Path) -> Iterator[Violation]:
    """Check a single Python file for violations."""
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        print(f"Warning: Could not read {path}: {e}", file=sys.stderr)
        return

    source_lines = source.splitlines()

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as e:
        print(f"Warning: Could not parse {path}: {e}", file=sys.stderr)
        return

    visitor = DelayCallVisitor(source_lines)
    visitor.visit(tree)

    for line, col, method in visitor.violations:
        source_line = source_lines[line - 1] if line <= len(source_lines) else ""
        yield Violation(
            path=path,
            line=line,
            col=col,
            method=method,
            source_line=source_line.strip(),
        )


def check_paths(paths: list[Path], exclude: set[str] | None = None) -> Iterator[Violation]:
    """Check multiple paths (files or directories) for violations."""
    exclude = exclude or set()

    for path in paths:
        if path.is_file():
            if path.suffix == ".py":
                yield from check_file(path)
        elif path.is_dir():
            for py_file in path.rglob("*.py"):
                # Check exclusions
                skip = False
                for exc in exclude:
                    if exc in str(py_file):
                        skip = True
                        break
                if not skip:
                    yield from check_file(py_file)


def main(args: list[str] | None = None) -> int:
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="airlock-lint",
        description="Detect direct .delay() and .apply_async() calls that bypass airlock.",
    )
    parser.add_argument(
        "paths",
        nargs="+",
        type=Path,
        help="Files or directories to check",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Patterns to exclude (can be repeated)",
    )

    parsed = parser.parse_args(args)

    violations = list(check_paths(parsed.paths, exclude=set(parsed.exclude)))

    for v in violations:
        print(v)

    if violations:
        print(f"\nFound {len(violations)} violation(s)", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
