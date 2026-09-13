"""AST-based safety validator for custom tool code.

Replaces the denylist-based ``validate_code_safety`` in
:class:`LLMTool <airunner_services.database.models.llm_tool.LLMTool>`
with an allowlist approach: the code is parsed into an AST and every
node is checked against a permitted set of constructs.

.. warning::

   Restricting ``__builtins__`` is **not** a complete sandbox.  Python
   code can escape via attribute traversal on any reachable object
   (``().__class__.__mro__[-1].__subclasses__()``).  The AST validator
   blocks the known bypass classes (literal attribute access, f-string
   smuggling, and ``str.format()`` field-name attribute traversal), but
   an attacker who controls the full code string and has access to any
   function object can potentially reach dangerous state through
   channels not covered here (e.g. ``%``-formatting with a pre-built
   dict, ``vars()``-adjacent tricks, or metaclass shenanigans).

   The long-term fix is subprocess isolation.  Until then, this module
   raises the bar from trivial substring-evasion to AST-level analysis.

Only the constructs genuinely needed by custom tool definitions
(function decorators, argument literals, simple expressions) are
allowed; everything else — imports, attribute traversal, dunder access,
f-string eval smuggling, ``str.format()`` field-name smuggling,
``exec``/``eval``/``compile``, ``__import__``, and any other dynamic
execution — is blocked before the code reaches ``exec()``.
"""

from __future__ import annotations

import ast
import re
from typing import Optional


# ---------------------------------------------------------------------------
# Permitted AST node types for custom tool definitions
# ---------------------------------------------------------------------------

_ALLOWED_NODE_TYPES: frozenset[type] = frozenset({
    # Module-level
    ast.Module,
    ast.FunctionDef,
    ast.arguments,
    ast.arg,
    ast.Load,
    ast.Store,
    ast.Param,
    # Decorators
    ast.Call,
    ast.Attribute,
    ast.Name,
    # Literals
    ast.Constant,
    ast.List,
    ast.Tuple,
    ast.Dict,
    ast.Set,
    ast.Starred,
    # Expressions
    ast.Expr,
    ast.BinOp,
    ast.UnaryOp,
    ast.BoolOp,
    ast.Compare,
    ast.IfExp,
    ast.Slice,
    ast.Subscript,
    # Operators
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Mod,
    ast.Pow,
    ast.FloorDiv,
    ast.MatMult,
    ast.LShift,
    ast.RShift,
    ast.BitOr,
    ast.BitXor,
    ast.BitAnd,
    ast.Invert,
    ast.Not,
    ast.UAdd,
    ast.USub,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.Is,
    ast.IsNot,
    ast.In,
    ast.NotIn,
    ast.And,
    ast.Or,
    # Compound statements
    ast.Return,
    ast.Assign,
    ast.AugAssign,
    ast.AnnAssign,
    ast.Pass,
    ast.If,
    ast.For,
    ast.While,
    ast.Break,
    ast.Continue,
    ast.With,
    ast.withitem,
    ast.Raise,
    ast.Try,
    ast.TryStar,
    ast.ExceptHandler,
    ast.Assert,
    ast.Delete,
    # Comprehensions
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
    ast.comprehension,
    # Strings (f-strings checked separately for eval smuggling)
    ast.FormattedValue,
    ast.JoinedStr,
    # Keywords
    ast.keyword,
    # Type hints
    ast.Subscript,
    ast.Name,
})


# ---------------------------------------------------------------------------
# Block-listed builtin names inside custom tool code
# ---------------------------------------------------------------------------

_FORBIDDEN_BUILTINS: frozenset[str] = frozenset({
    "eval",
    "exec",
    "compile",
    "__import__",
    "open",
    "input",
    "breakpoint",
    "memoryview",
    "staticmethod",
    "classmethod",
    "property",
    "super",
    "globals",
    "locals",
    "vars",
    "dir",
    "getattr",
    "setattr",
    "delattr",
    "type",
    "object",
    "__build_class__",
})

# Attribute / dunder names that must not appear anywhere — shared
# between literal ``ast.Attribute`` checks and ``str.format()``
# field-name string-scanning.
_FORBIDDEN_ATTRS: frozenset[str] = frozenset({
    "__class__",
    "__bases__",
    "__base__",
    "__mro__",
    "__subclasses__",
    "__globals__",
    "__code__",
    "__func__",
    "__self__",
    "__dict__",
    "__builtins__",
    "__import__",
    "__loader__",
    "__spec__",
    "__path__",
    "__file__",
    "__cached__",
    "__name__",
    "__qualname__",
    "__module__",
    "__annotations__",
    "__closure__",
    "__defaults__",
    "__kwdefaults__",
    "__init__",
    "__new__",
    "__del__",
    "__reduce__",
    "__reduce_ex__",
    "__getstate__",
    "__setstate__",
    "__getattr__",
    "__setattr__",
    "__delattr__",
    "__call__",
    "__enter__",
    "__exit__",
})

# Regex matching any forbidden attribute name inside a str.format()
# field name (e.g. {0.__globals__}, {0.__init__.__globals__}).
# The field-name portion between { and } (or {0. and }) is scanned
# for these dunder names — they resolve attribute access at runtime
# without ever producing an ast.Attribute node.
_FORMAT_FIELD_DUNDER_RE = re.compile(
    r"\.\s*(" + "|".join(map(re.escape, _FORBIDDEN_ATTRS)) + r")\b"
)


def _scan_format_string_for_dunders(
    fmt_string: str,
    lineno: int = 0,
) -> Optional[str]:
    """Return the first forbidden dunder found in *fmt_string* field
    names, or ``None`` if the format string is clean."""
    # Extract field names from {field_name!conv:format_spec} patterns.
    # Built-in re won't do balanced braces, but a simple scan covers
    # the common attack patterns.
    parts = re.split(r"\{([^}]*)\}", fmt_string)
    # Every odd-indexed element is the content between braces.
    for i in range(1, len(parts), 2):
        field = parts[i]
        match = _FORMAT_FIELD_DUNDER_RE.search(field)
        if match:
            return (
                f"Forbidden dunder '{match.group(1)}' in "
                f"str.format() field name at line {lineno}"
            )
    return None


def validate_code_safety_ast(code: str) -> tuple[bool, str]:
    """Parse *code* as Python and validate every AST node is permitted.

    Returns ``(True, "")`` when the code is safe, or
    ``(False, reason)`` when a forbidden construct is found.

    This replaces the simple substring-match denylist in
    ``LLMTool.validate_code_safety`` with AST-level analysis that
    cannot be bypassed with string obfuscation, whitespace tricks,
    or comments.
    """
    if not code or not code.strip():
        return False, "Code is empty"

    # ── Quick-reject by line for exec/eval/compile ──────────────
    for line in code.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if stripped.startswith(("exec(", "exec ", "eval(", "eval ")):
            return False, "Direct exec/eval call detected"

    # ── Parse the AST ───────────────────────────────────────────
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        return False, f"Syntax error: {exc}"

    # ── Walk every node ─────────────────────────────────────────
    for node in ast.walk(tree):
        lineno = getattr(node, "lineno", 0)

        # 1. Check node type is allowed.
        if type(node) not in _ALLOWED_NODE_TYPES:
            return False, (
                f"Forbidden construct: {type(node).__name__} "
                f"at line {lineno}"
            )

        # 2. Block Import / ImportFrom.
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return False, "Import statements are not allowed"

        # 3. Block forbidden attribute access in literal AST nodes.
        if isinstance(node, ast.Attribute):
            if isinstance(node.attr, str) and node.attr in _FORBIDDEN_ATTRS:
                return False, (
                    f"Forbidden attribute: '{node.attr}' "
                    f"at line {lineno}"
                )

        # 4. Block forbidden builtin names.
        if isinstance(node, ast.Name):
            if isinstance(node.id, str) and node.id in _FORBIDDEN_BUILTINS:
                return False, (
                    f"Forbidden builtin: '{node.id}' "
                    f"at line {lineno}"
                )

        # 5. Block f-string eval smuggling: scan value, conversion,
        #    and format_spec sub-nodes of every FormattedValue.
        if isinstance(node, ast.FormattedValue):
            for inner in ast.walk(node.value):
                if isinstance(inner, ast.Name):
                    if (
                        isinstance(inner.id, str)
                        and inner.id in _FORBIDDEN_BUILTINS
                    ):
                        return False, (
                            f"Forbidden builtin '{inner.id}' in "
                            f"f-string at line {lineno}"
                        )
                if isinstance(inner, ast.Attribute):
                    if (
                        isinstance(inner.attr, str)
                        and inner.attr in _FORBIDDEN_ATTRS
                    ):
                        return False, (
                            f"Forbidden attribute '{inner.attr}' in "
                            f"f-string at line {lineno}"
                        )
                if isinstance(inner, ast.Call):
                    return False, (
                        "Function calls are not allowed inside "
                        "f-string expressions"
                    )
            # Also scan the format_spec (the part after `:` in
            # e.g. f"{x:>10}" or more dangerously f"{x:{y}.__globals__}").
            if node.format_spec is not None:
                for inner in ast.walk(node.format_spec):
                    if isinstance(inner, ast.Attribute):
                        if (
                            isinstance(inner.attr, str)
                            and inner.attr in _FORBIDDEN_ATTRS
                        ):
                            return False, (
                                f"Forbidden attribute '{inner.attr}' "
                                f"in f-string format spec at line "
                                f"{lineno}"
                            )
                    if isinstance(inner, ast.Call):
                        return False, (
                            "Function calls are not allowed in "
                            "f-string format spec"
                        )

        # 6. Block str.format() / str.format_map() field-name dunder
        #    smuggling.  ``"{0.__globals__}".format(x)`` resolves
        #    ``__globals__`` at runtime from the format string — no
        #    ``ast.Attribute`` node is ever produced.
        if isinstance(node, ast.Call):
            # .format() / .format_map() called on a string constant.
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr in ("format", "format_map")
                and isinstance(node.func.value, ast.Constant)
                and isinstance(node.func.value.value, str)
            ):
                reason = _scan_format_string_for_dunders(
                    node.func.value.value, lineno,
                )
                if reason:
                    return False, reason
            # format() called as a free function on a string constant.
            elif (
                isinstance(node.func, ast.Name)
                and node.func.id == "format"
                and len(node.args) >= 1
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                reason = _scan_format_string_for_dunders(
                    node.args[0].value, lineno,
                )
                if reason:
                    return False, reason

        # 7. ClassDef — custom tools should only define functions.
        if isinstance(node, ast.ClassDef):
            return False, "Class definitions are not allowed"

        # 8. Lambda — unnecessary in tool definitions, often used
        #    for obfuscation.
        if isinstance(node, ast.Lambda):
            return False, "Lambda expressions are not allowed"

    # ── Check that the decorator is @tool ─────────────────────
    has_tool = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Name) and decorator.id == "tool":
                has_tool = True
                break
            if (
                isinstance(decorator, ast.Attribute)
                and decorator.attr == "tool"
            ):
                has_tool = True
                break
    if not has_tool:
        return False, "Code must contain at least one @tool-decorated function"

    return True, ""
