#!/usr/bin/env python3
"""Check that decomposing a module into a package preserved its public
interface: every module-level name the original file exposed must be
re-exported (or defined) by the package's __init__.py.

Pure-ast comparison, no imports executed — safe to run on any pair of
files. Usage:

    python scripts/check_re_exports.py <original_file.py> <package_dir/>

Exits 0 if every module-level name of the original is present in the
package namespace, 1 and prints the missing names otherwise.

Used by the parallel-worktree orchestrator to independently audit the
re-export shims created by issue #27 decompositions (this caught a real
gap: _ART_JOB_POLL_INTERVAL_SECONDS was not re-exported by
_gui_daemon_client/__init__.py).
"""

import ast
import sys


def defined_names(path: str) -> set:
    """Return module-level names the file DEFINES (classes, functions,
    constants via assignment) — the public surface it provides.

    Imported names are deliberately excluded: a module importing `os` or
    a typing name is not thereby exposing it as interface, and requiring
    re-export of every transitive import would be noise.
    """
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=path)
    names: set = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.ImportFrom) and node.module == "__future__":
            continue
    return names


def all_module_level_names(path: str) -> set:
    """All module-level names (defined or imported) — informational."""
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=path)
    names: set = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
    return names


def main() -> int:
    if len(sys.argv) != 3:
        print(
            "usage: check_re_exports.py <original_file.py> <package_dir/>",
            file=sys.stderr,
        )
        return 2
    orig_path, pkg_dir = sys.argv[1], sys.argv[2]
    init_path = f"{pkg_dir.rstrip('/')}/__init__.py"

    original_defined = defined_names(orig_path)
    # Re-export surface = names in __init__.py itself (including its own
    # `from ... import X` lines, which the AST captures as ImportFrom).
    package = all_module_level_names(init_path)

    missing = sorted(original_defined - package)
    if not missing:
        print(f"OK: all {len(original_defined)} names defined by {orig_path}")
        print("    are present in the package namespace.")
        return 0
    print(f"MISSING from package namespace ({len(missing)} defined-by-original names):")
    for name in missing:
        print(f"  {name}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
