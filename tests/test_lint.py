"""Tests for the airlock linter."""

import tempfile
from pathlib import Path

import pytest

from airlock.lint import check_file, check_paths, Violation, main


class TestCheckFile:
    """Tests for single file checking."""

    def test_detects_delay_call(self):
        """Test that .delay() calls are detected."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("task.delay(123)\n")
            f.flush()

            violations = list(check_file(Path(f.name)))

        assert len(violations) == 1
        assert violations[0].method == "delay"
        assert violations[0].line == 1

    def test_detects_apply_async_call(self):
        """Test that .apply_async() calls are detected."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("task.apply_async(args=(1,))\n")
            f.flush()

            violations = list(check_file(Path(f.name)))

        assert len(violations) == 1
        assert violations[0].method == "apply_async"

    def test_detects_multiple_violations(self):
        """Test detection of multiple violations in one file."""
        code = """
def handler():
    task_a.delay(1)
    task_b.delay(2)
    task_c.apply_async(args=(3,))
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()

            violations = list(check_file(Path(f.name)))

        assert len(violations) == 3

    def test_noqa_suppresses_violation(self):
        """Test that # noqa: airlock suppresses violations."""
        code = """
task_a.delay(1)  # noqa: airlock
task_b.delay(2)
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()

            violations = list(check_file(Path(f.name)))

        assert len(violations) == 1
        assert violations[0].line == 3  # Only task_b

    def test_noqa_case_insensitive(self):
        """Test that noqa comment is case-insensitive."""
        code = "task.delay(1)  # NOQA: AIRLOCK\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()

            violations = list(check_file(Path(f.name)))

        assert len(violations) == 0

    def test_noqa_without_space(self):
        """Test that # noqa:airlock (no space) works."""
        code = "task.delay(1)  # noqa:airlock\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()

            violations = list(check_file(Path(f.name)))

        assert len(violations) == 0

    def test_noqa_with_airlock_elsewhere(self):
        """Test that # noqa with airlock elsewhere on line works."""
        code = "task.delay(1)  # noqa - airlock migration\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()

            violations = list(check_file(Path(f.name)))

        assert len(violations) == 0

    def test_handles_unreadable_file(self):
        """Test graceful handling of unreadable files."""
        import os
        # Skip if running as root (can read any file)
        if os.geteuid() == 0:
            pytest.skip("Cannot test file permissions as root")

        # Create a file then make it unreadable
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("task.delay(1)\n")
            path = Path(f.name)

        # Remove read permissions
        path.chmod(0o000)
        try:
            violations = list(check_file(path))
            # Should return empty, not raise
            assert len(violations) == 0
        finally:
            # Restore permissions for cleanup
            path.chmod(0o644)
            path.unlink()

    def test_no_false_positives_on_other_methods(self):
        """Test that other .method() calls are not flagged."""
        code = """
obj.save()
obj.delete()
list.append(1)
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()

            violations = list(check_file(Path(f.name)))

        assert len(violations) == 0

    def test_handles_syntax_errors(self):
        """Test graceful handling of syntax errors."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("def broken(\n")  # Invalid syntax
            f.flush()

            violations = list(check_file(Path(f.name)))

        # Should return empty, not raise
        assert len(violations) == 0

    def test_airlock_enqueue_not_flagged(self):
        """Test that airlock.enqueue() is not flagged."""
        code = """
import airlock
airlock.enqueue(my_task, 123)
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()

            violations = list(check_file(Path(f.name)))

        assert len(violations) == 0


class TestCheckPaths:
    """Tests for checking multiple paths."""

    def test_checks_directory_recursively(self):
        """Test recursive directory checking."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create nested structure
            subdir = Path(tmpdir) / "subdir"
            subdir.mkdir()

            (Path(tmpdir) / "a.py").write_text("task.delay(1)\n")
            (subdir / "b.py").write_text("task.delay(2)\n")

            violations = list(check_paths([Path(tmpdir)]))

        assert len(violations) == 2

    def test_exclude_pattern(self):
        """Test exclusion of paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "good.py").write_text("task.delay(1)\n")
            (Path(tmpdir) / "test_something.py").write_text("task.delay(2)\n")

            violations = list(check_paths([Path(tmpdir)], exclude={"test_"}))

        assert len(violations) == 1

    def test_skips_non_python_files(self):
        """Test that non-Python files are skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "script.py").write_text("task.delay(1)\n")
            (Path(tmpdir) / "readme.md").write_text("task.delay(1)\n")
            (Path(tmpdir) / "config.json").write_text('{"delay": 1}')

            violations = list(check_paths([Path(tmpdir)]))

        assert len(violations) == 1

    def test_single_file_path(self):
        """Test checking a single file path directly."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("task.delay(1)\ntask.apply_async()\n")
            f.flush()
            path = Path(f.name)

        try:
            violations = list(check_paths([path]))
            assert len(violations) == 2
        finally:
            path.unlink()

    def test_single_non_python_file_skipped(self):
        """Test that a single non-Python file is skipped."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("task.delay(1)\n")
            f.flush()
            path = Path(f.name)

        try:
            violations = list(check_paths([path]))
            assert len(violations) == 0
        finally:
            path.unlink()


class TestMain:
    """Tests for CLI entry point."""

    def test_returns_zero_on_no_violations(self):
        """Test exit code 0 when clean."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "clean.py").write_text("import airlock\n")

            result = main([tmpdir])

        assert result == 0

    def test_returns_one_on_violations(self):
        """Test exit code 1 when violations found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "bad.py").write_text("task.delay(1)\n")

            result = main([tmpdir])

        assert result == 1


class TestViolationFormatting:
    """Tests for violation string formatting."""

    def test_violation_str_format(self):
        """Test violation string representation."""
        v = Violation(
            path=Path("src/tasks.py"),
            line=42,
            col=8,
            method="delay",
            source_line="my_task.delay(123)",
        )

        s = str(v)
        assert "src/tasks.py:42:8" in s
        assert "AIR001" in s
        assert ".delay()" in s
