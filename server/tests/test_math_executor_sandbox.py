"""Tests for round-3 Python executor sandbox hardening.

Covers:
- .format() attribute-traversal escape blocked
- f-string attribute-traversal escape blocked
- str.format_map() blocked
- _check_dangerous_operations wired up in execute()
"""
from __future__ import annotations

import pytest

from airunner_services.eval.math_tools._executor import SafePythonExecutor


class TestValidateCodeFormatEscape:
    """validate_code() must reject str.format() sandbox escapes."""

    def setup_method(self) -> None:
        self.executor = SafePythonExecutor()

    # -- safe code still passes ------------------------------------------

    def test_simple_math_passes(self) -> None:
        safe, msg = self.executor.validate_code("result = 1 + 1")
        assert safe, f"Expected safe, got: {msg}"

    def test_sympy_import_passes(self) -> None:
        safe, msg = self.executor.validate_code(
            "import sympy as sp\nresult = sp.symbols('x')",
        )
        assert safe, f"Expected safe, got: {msg}"

    # -- .format() escape blocked ----------------------------------------

    @pytest.mark.parametrize(
        "code",
        [
            # Direct .format() attribute traversal
            (
                "result = '{0.__class__.__base__.__subclasses__}'"
                ".format(())"
            ),
            # .format_map() variant
            (
                "result = '{0.__class__}'.format_map({0: ()})"
            ),
            # .format() on an f-string-like literal
            "x = '{.__class__}'.format",
            # Nested format spec
            (
                "result = '{0.__class__.__base__}"
                "{0.__class__.__base__}'.format(())"
            ),
        ],
    )
    def test_format_escape_rejected(self, code: str) -> None:
        safe, msg = self.executor.validate_code(code)
        assert not safe, (
            f"Expected format escape to be rejected, but it passed.\n"
            f"Code: {code!r}\n"
            f"Message: {msg}"
        )

    # -- f-string escape blocked ------------------------------------------

    @pytest.mark.parametrize(
        "code",
        [
            # f-string with attribute traversal
            'result = f"{().__class__.__base__.__subclasses__}"',
            # f-string with nested format
            'x = (); result = f"{x.__class__}"',
        ],
    )
    def test_fstring_escape_rejected(self, code: str) -> None:
        safe, msg = self.executor.validate_code(code)
        assert not safe, (
            f"Expected f-string escape to be rejected, but it passed.\n"
            f"Code: {code!r}\n"
            f"Message: {msg}"
        )

    # -- dunder string literal blocked ------------------------------------

    def test_dunder_string_literal_rejected(self) -> None:
        safe, msg = self.executor.validate_code(
            'x = "__class__.__base__"',
        )
        assert not safe, (
            f"Expected dunder string literal to be rejected.\n"
            f"Message: {msg}"
        )


class TestValidateCodeDirectDunderStillRejected:
    """Direct dunder attribute access is still blocked (was already)."""

    def setup_method(self) -> None:
        self.executor = SafePythonExecutor()

    def test_direct_dunder_access_rejected(self) -> None:
        safe, msg = self.executor.validate_code(
            "x = ().__class__.__base__.__subclasses__()",
        )
        assert not safe, (
            f"Expected direct dunder access to be rejected.\n"
            f"Message: {msg}"
        )


class TestDangerousOperationsWiredUp:
    """_check_dangerous_operations must be called in execute()."""

    def setup_method(self) -> None:
        self.executor = SafePythonExecutor()

    def test_os_import_rejected_in_execute(self) -> None:
        success, result, msg = self.executor.execute(
            "import os\nresult = os.getcwd()",
        )
        assert not success, (
            f"Expected os import to be rejected in execute().\n"
            f"Got: success={success}, result={result}, msg={msg!r}"
        )
        assert "Dangerous operation" in msg

    def test_eval_call_rejected_in_execute(self) -> None:
        success, result, msg = self.executor.execute(
            'result = eval("1+1")',
        )
        assert not success, (
            f"Expected eval() to be rejected in execute().\n"
            f"Got: success={success}, result={result}, msg={msg!r}"
        )

    def test_exec_call_rejected_in_execute(self) -> None:
        success, result, msg = self.executor.execute(
            'exec("x=1")\nresult = 0',
        )
        assert not success, (
            f"Expected exec() to be rejected in execute().\n"
            f"Got: success={success}, result={result}, msg={msg!r}"
        )


class TestSafeCodeStillExecutes:
    """Legitimate math code must still work."""

    def setup_method(self) -> None:
        self.executor = SafePythonExecutor()

    def test_basic_arithmetic(self) -> None:
        success, result, msg = self.executor.execute("result = 2 + 2")
        assert success, f"Expected success, got: {msg}"
        assert result == 4, f"Expected 4, got: {result}"

    def test_import_math(self) -> None:
        success, result, msg = self.executor.execute(
            "import math\nresult = math.sqrt(16)",
        )
        assert success, f"Expected success, got: {msg}"
        assert result == 4.0, f"Expected 4.0, got: {result}"
