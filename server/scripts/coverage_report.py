#!/usr/bin/env python3
"""Generate a line-coverage report for a specific set of source files.

Unlike ``run_tests.py`` (which runs whole suites), this is a narrow tool:
point it at the source file(s) you're trying to fully cover and the test
file(s)/dir(s) that exercise them, and it reports exactly which lines are
still missing coverage.  Intended to be re-run in a loop while iterating
on a test suite until coverage converges.

Must be run inside the server container from /app (needs the
``coverage`` package and the project's Python environment). This file
lives under ``server/scripts/`` (not the top-level ``scripts/``)
because only ``./server``, ``./extensions``, and ``./projects`` are
bind-mounted into the container — see docker-compose.yml.

    docker compose exec server python server/scripts/coverage_report.py \\
        --src server/src/airunner_services/utils/crypto/user_envelope.py \\
        --src server/src/airunner_services/utils/crypto/user_encrypted_type.py \\
        --src server/src/airunner_services/utils/crypto/dek_cache.py \\
        --test server/src/airunner_services/tests/unit/test_user_envelope.py \\
        --test server/src/airunner_services/tests/unit/test_user_encrypted_type.py \\
        --test server/src/airunner_services/tests/unit/test_dek_cache.py \\
        --test extensions/auth/tests/test_routes.py

Exits non-zero if any --src file is below --min-percent (default: 100),
so it can be used as a pass/fail gate in an iteration loop, e.g.:

    until docker compose exec server python server/scripts/coverage_report.py \\
        --src ... --test ...; do
        echo "coverage incomplete — hand the report back to deepseek"
        break
    done
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    print(f"$ {' '.join(cmd)}")
    return subprocess.run(cmd, capture_output=True, text=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--src",
        action="append",
        required=True,
        dest="sources",
        help="Source file to measure coverage for (repeatable).",
    )
    parser.add_argument(
        "--test",
        action="append",
        required=True,
        dest="tests",
        help="Test file or directory to run (repeatable).",
    )
    parser.add_argument(
        "--min-percent",
        type=float,
        default=100.0,
        help="Fail if any --src file's coverage is below this (default 100).",
    )
    parser.add_argument(
        "--html",
        action="store_true",
        help="Also write an HTML report to htmlcov/ for browsing.",
    )
    args = parser.parse_args()

    subprocess.run(["coverage", "erase"], check=False)

    # Deliberately no --source restriction on the run step: passing literal
    # file paths to `coverage run --source=` does not reliably match how
    # pytest resolves imports in this project (conftest.py sys.path setup
    # causes a module-not-imported false negative). Measure everything and
    # filter down with --include at the report step instead, which does
    # match correctly.
    run_cmd = [
        "coverage",
        "run",
        "--branch",
        "-m",
        "pytest",
        "-q",
        *args.tests,
    ]
    result = _run(run_cmd)
    print(result.stdout)
    print(result.stderr, file=sys.stderr)
    if result.returncode != 0:
        print(
            f"\n(!) pytest exited {result.returncode} — fix failing tests "
            "before chasing coverage numbers.",
            file=sys.stderr,
        )

    report_cmd = ["coverage", "report", "-m", "--include=" + ",".join(args.sources)]
    report = _run(report_cmd)
    print(report.stdout)
    if report.returncode != 0:
        print(report.stderr, file=sys.stderr)
        return 1

    if args.html:
        subprocess.run(
            ["coverage", "html", "--include=" + ",".join(args.sources)],
            check=False,
        )
        print("HTML report written to htmlcov/index.html")

    # Parse per-file percentages from `coverage json`, not the text table —
    # the text table's trailing "Missing" column has a variable number of
    # fields (line ranges), so naively splitting on whitespace and taking
    # the last token silently grabs a line-range string instead of the
    # percentage once -m/--branch produce a Missing column.
    json_result = _run(
        ["coverage", "json", "-o", "-", "--include=" + ",".join(args.sources)]
    )
    if json_result.returncode != 0:
        print(json_result.stderr, file=sys.stderr)
        return 1
    data = json.loads(json_result.stdout)

    failed: list[tuple[str, float]] = []
    for path, file_data in data.get("files", {}).items():
        pct = file_data["summary"]["percent_covered"]
        if pct < args.min_percent:
            failed.append((path, pct))

    if failed:
        print(
            f"\nBelow {args.min_percent:.0f}% coverage "
            f"({len(failed)} file(s)):"
        )
        for path, pct in failed:
            print(f"  {path}: {pct:.0f}%")
        return 1

    print(f"\nAll source files at or above {args.min_percent:.0f}% coverage.")
    return 0 if result.returncode == 0 else result.returncode


if __name__ == "__main__":
    sys.exit(main())
