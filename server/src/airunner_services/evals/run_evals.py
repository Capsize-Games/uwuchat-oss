#!/usr/bin/env python3
"""Minimal eval runner for persona and memory coherence test suites.

Usage:
    docker compose exec server python \\
        -m airunner_services.evals.run_evals

The runner instantiates each eval class, runs every ``test_*`` method,
and prints PASS/FAIL with assertion details.  Exits with code 1 when
any test fails so it works in CI.
"""

from __future__ import annotations

import sys
from typing import List, Tuple

from airunner_services.evals.persona_fidelity_eval import PersonaFidelityEval
from airunner_services.evals.persona_fidelity_eval_ext import (
    PersonaFidelityEvalExt,
)
from airunner_services.evals.memory_coherence_eval import (
    MemoryCoherenceEval,
)
from airunner_services.evals.memory_coherence_eval_ext import (
    MemoryCoherenceEvalExt,
)
from airunner_services.evals.persona_honesty_eval import (
    PersonaHonestyEval,
)


def _print_header(title: str) -> None:
    """Print a section header."""
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def _run_suite(
    suite_name: str,
    instance: object,
) -> Tuple[int, int]:
    """Run one test suite and print results.

    Returns:
        (passed_count, failed_count)
    """
    _print_header(suite_name)
    results: List[Tuple[str, bool, str]] = instance.run_all()
    passed = 0
    failed = 0
    for name, ok, detail in results:
        if ok:
            print(f"  PASS  {name}")
            passed += 1
        else:
            print(f"  FAIL  {name}")
            print(f"        {detail}")
            failed += 1
    return passed, failed


def main() -> int:
    """Run both eval suites and report aggregate results."""
    total_pass = 0
    total_fail = 0

    pf_pass, pf_fail = _run_suite(
        "Persona Fidelity",
        PersonaFidelityEval(),
    )
    total_pass += pf_pass
    total_fail += pf_fail

    pf2_pass, pf2_fail = _run_suite(
        "Persona Fidelity (extended)",
        PersonaFidelityEvalExt(),
    )
    total_pass += pf2_pass
    total_fail += pf2_fail

    mc_pass, mc_fail = _run_suite(
        "Memory Coherence",
        MemoryCoherenceEval(),
    )
    total_pass += mc_pass
    total_fail += mc_fail

    mc2_pass, mc2_fail = _run_suite(
        "Memory Coherence (extended)",
        MemoryCoherenceEvalExt(),
    )
    total_pass += mc2_pass
    total_fail += mc2_fail

    ph_pass, ph_fail = _run_suite(
        "Persona Honesty",
        PersonaHonestyEval(),
    )
    total_pass += ph_pass
    total_fail += ph_fail

    print(f"\n{'=' * 60}")
    print(f"  TOTAL:  {total_pass} passed, {total_fail} failed")
    print(f"{'=' * 60}")

    return 1 if total_fail > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
