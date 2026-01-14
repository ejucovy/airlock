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

    def test_detects_inline_import(self):
        code = """
def foo():
    import bar
"""
        errors = check(code)
        assert len(errors) == 1
        assert "AIR002" in errors[0][2]

    def test_detects_inline_import_from(self):
        code = """
def foo():
    from bar import baz
"""
        errors = check(code)
        assert len(errors) == 1
        assert "AIR002" in errors[0][2]

    def test_detects_inline_import_in_async_function(self):
        code = """
async def foo():
    import bar
"""
        errors = check(code)
        assert len(errors) == 1
        assert "AIR002" in errors[0][2]

    def test_ignores_top_level_import(self):
        code = """
import bar
def foo():
    pass
"""
        errors = check(code)
        assert len(errors) == 0

    def test_multiple_inline_imports(self):
        code = """
def foo():
    import bar
    from baz import qux
"""
        errors = check(code)
        assert len(errors) == 2


class TestCheckFile:
    def test_check_file_with_source(self, tmp_path):
        from pathlib import Path
        from airlock.flake8_plugin import check_file

        source = "def foo():\n    import bar\n"
        violations = check_file(Path("test.py"), source=source)
        assert len(violations) == 1
        assert violations[0][1] == 2  # line 2
        assert "AIR002" in violations[0][3]

    def test_check_file_reads_file(self, tmp_path):
        from airlock.flake8_plugin import check_file

        filepath = tmp_path / "test.py"
        filepath.write_text("def foo():\n    import bar\n")
        violations = check_file(filepath)
        assert len(violations) == 1

    def test_noqa_suppresses_violation(self, tmp_path):
        from pathlib import Path
        from airlock.flake8_plugin import check_file

        source = "def foo():\n    import bar  # noqa: AIR002\n"
        violations = check_file(Path("test.py"), source=source)
        assert len(violations) == 0

    def test_noqa_case_insensitive(self, tmp_path):
        from pathlib import Path
        from airlock.flake8_plugin import check_file

        source = "def foo():\n    import bar  # NOQA\n"
        violations = check_file(Path("test.py"), source=source)
        assert len(violations) == 0


class TestMain:
    def test_main_returns_zero_on_clean_codebase(self):
        """main() should return 0 since airlock has noqa on legitimate inline imports."""
        from airlock.flake8_plugin import main

        # The airlock codebase should pass (noqa comments in place)
        assert main() == 0

    def test_main_prints_violations_and_returns_one(self, tmp_path, monkeypatch, capsys):
        """Test main() prints violations and returns 1 when issues found."""
        import airlock.flake8_plugin as plugin_module

        # Create a temp file with a violation
        bad_file = tmp_path / "bad.py"
        bad_file.write_text("def foo():\n    import bar\n")

        # Create a fake flake8_plugin.py in tmp_path so Path(__file__).parent works
        fake_plugin = tmp_path / "flake8_plugin.py"
        fake_plugin.write_text("")

        # Monkey-patch __file__ in the module
        original_file = plugin_module.__file__
        monkeypatch.setattr(plugin_module, "__file__", str(fake_plugin))

        # Now main() will scan tmp_path and find bad.py
        from airlock.flake8_plugin import main
        result = main()

        # Restore
        monkeypatch.setattr(plugin_module, "__file__", original_file)

        assert result == 1
        captured = capsys.readouterr()
        assert "AIR002" in captured.out
        assert "bad.py" in captured.out

    def test_module_main_block(self):
        """Test that running as __main__ calls main() and exits."""
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, "-m", "airlock.flake8_plugin"],
            capture_output=True,
            text=True,
        )
        # Should exit 0 since airlock codebase is clean (noqa in place)
        assert result.returncode == 0
