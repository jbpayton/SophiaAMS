#!/usr/bin/env python3
"""
SOPHIA AMS v2 — Scored Test Report Runner

Run:  python tests/run_report.py
Save: python tests/run_report.py > reports/2026-02-21.txt

With live E2E (requires LLM server):
  python tests/run_report.py --with-e2e

Produces a fixed-width, diffable test report with weighted category scores.
Exit code: 0 if 100%, 1 otherwise.
"""

import argparse
import datetime
import importlib
import os
import platform
import sys
import unittest

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ---------------------------------------------------------------------------
# Category definitions: (label, module_name, weight)
# ---------------------------------------------------------------------------
CATEGORIES = [
    ("LLM Interface",           "tests.test_llm_client",                1.0),
    ("Code Execution",          "tests.test_code_runner",               1.0),
    ("Conversation Management", "tests.test_conversation_memory",       1.0),
    ("Skill System",            "tests.test_skill_loader",              1.0),
    ("Memory Middleware",       "tests.test_stream_monitor",            1.0),
    ("Agent Loop",              "tests.test_agent_loop",                1.0),
    ("Workspace",               "tests.test_workspace_init",            1.0),
    ("Orchestration",           "tests.test_sophia_agent_v2",           1.0),
    ("API Integration",         "tests.test_agent_server_integration",  1.5),
    ("Torture Test",            "tests.test_torture",                   2.0),
]

LABEL_WIDTH = 30
LINE_WIDTH = 64


# ---------------------------------------------------------------------------
# Custom TestResult that collects counts without printing dots
# ---------------------------------------------------------------------------
class _ScoringResult(unittest.TestResult):
    """Collects pass/fail/error/skip counts silently."""

    def __init__(self):
        super().__init__()
        self.passed = 0
        self.fail_details = []  # list of (test_id, traceback_str)
        self.error_details = []

    def startTest(self, test):
        super().startTest(test)

    def addSuccess(self, test):
        super().addSuccess(test)
        self.passed += 1

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.fail_details.append((str(test), self._exc_info_to_string(err, test)))

    def addError(self, test, err):
        super().addError(test, err)
        self.error_details.append((str(test), self._exc_info_to_string(err, test)))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)

    @property
    def total(self):
        return self.passed + len(self.failures) + len(self.errors) + len(self.skipped)

    @property
    def fail_count(self):
        return len(self.failures)

    @property
    def error_count(self):
        return len(self.errors)

    @property
    def skip_count(self):
        return len(self.skipped)

    @property
    def score(self):
        if self.total == 0:
            return 0.0
        return self.passed / self.total * 100.0


# ---------------------------------------------------------------------------
# Modules that get contaminated by sys.modules mocking in integration tests
# ---------------------------------------------------------------------------
_CONTAMINATED_MODULES = [
    "sophia_agent", "llm_client", "code_runner", "conversation_memory",
    "skill_loader", "stream_monitor", "agent_loop", "workspace_init",
    "agent_server",
]


# ---------------------------------------------------------------------------
# Run a single category
# ---------------------------------------------------------------------------
def _run_category(module_name: str, cleanup_after: bool = False) -> _ScoringResult:
    """Import module, discover tests, run them, return result."""
    loader = unittest.TestLoader()
    result = _ScoringResult()

    try:
        mod = importlib.import_module(module_name)
        suite = loader.loadTestsFromModule(mod)
        suite.run(result)
    except Exception as e:
        # If module can't import, record as error
        result.error_details.append((module_name, str(e)))

    if cleanup_after:
        # Remove modules that may have been contaminated by sys.modules mocking
        for mod_name in list(sys.modules):
            if mod_name in _CONTAMINATED_MODULES or mod_name == module_name:
                del sys.modules[mod_name]

    return result


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------
def _render_report(results: list[tuple[str, float, _ScoringResult]]) -> str:
    """Build the full report string."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    py_ver = platform.python_version()
    plat = sys.platform

    lines = []
    sep = "=" * LINE_WIDTH

    lines.append(sep)
    lines.append("  SOPHIA AMS v2 -- TEST REPORT")
    lines.append(f"  Generated: {now}")
    lines.append(f"  Python: {py_ver} | Platform: {plat}")
    lines.append(sep)
    lines.append("")

    # Header
    header = f"{'CATEGORY':<{LABEL_WIDTH}}  PASS  FAIL  ERR  SKIP   SCORE"
    lines.append(header)
    lines.append("-" * LINE_WIDTH)

    total_passed = 0
    total_tests = 0
    weighted_sum = 0.0
    weight_sum = 0.0
    all_failures = []

    for label, weight, result in results:
        total_passed += result.passed
        total_tests += result.total
        weighted_sum += result.score * weight
        weight_sum += weight

        score_str = f"{result.score:5.1f}%"
        line = (
            f"{label:<{LABEL_WIDTH}}"
            f"  {result.passed:4d}"
            f"  {result.fail_count:4d}"
            f"  {result.error_count:3d}"
            f"  {result.skip_count:4d}"
            f"  {score_str:>7s}"
        )
        lines.append(line)

        # Collect failure details
        for test_id, tb in result.fail_details:
            all_failures.append(("FAIL", label, test_id, tb))
        for test_id, tb in result.error_details:
            all_failures.append(("ERROR", label, test_id, tb))

    lines.append("-" * LINE_WIDTH)
    lines.append("")

    # Overall scores
    weighted_overall = weighted_sum / weight_sum if weight_sum > 0 else 0.0
    raw_pct = (total_passed / total_tests * 100.0) if total_tests > 0 else 0.0

    lines.append(f"WEIGHTED OVERALL SCORE: {weighted_overall:.1f}%")
    lines.append(f"RAW OVERALL: {total_passed}/{total_tests} passed ({raw_pct:.1f}%)")
    lines.append("")

    # Failure details
    lines.append("FAILURES:")
    if not all_failures:
        lines.append("  (none)")
    else:
        for kind, category, test_id, tb in all_failures:
            lines.append(f"  [{kind}] {category} :: {test_id}")
            # Indent traceback
            for tb_line in tb.strip().split("\n"):
                lines.append(f"    {tb_line}")
            lines.append("")

    lines.append(sep)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# E2E integration — wraps e2e_scenarios results into _ScoringResult
# ---------------------------------------------------------------------------
def _run_e2e() -> _ScoringResult:
    """
    Run live E2E scenarios and return results as a _ScoringResult.
    Each scenario counts as one "test".
    """
    result = _ScoringResult()
    try:
        from tests.e2e_scenarios import run_e2e_scenarios
        passed, total, report_dir, logs = run_e2e_scenarios()

        result.passed = passed
        # Record failures as error_details so they show in the report
        for log in logs:
            if not log.passed:
                result.error_details.append(
                    (f"Scenario {log.number:02d}: {log.name}", log.error_msg or "FAIL")
                )
            # Increment the internal counters to make .total work
            # _ScoringResult.total = passed + failures + errors + skipped
            # We already set passed; errors are in error_details via addError path.
            # We need to add fake failure entries so .total is correct.

        # _ScoringResult uses len(self.failures) + len(self.errors) for counting.
        # We appended to error_details but not self.errors (the base class list).
        # Fix: directly set the base class errors list to match.
        result.errors = [(name, tb) for name, tb in result.error_details]
        result.error_details = [(name, tb) for name, tb in result.error_details]

        print(f"  E2E report: {report_dir}")

    except Exception as e:
        result.error_details.append(("e2e_scenarios", str(e)))
        result.errors = [("e2e_scenarios", str(e))]

    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="SOPHIA AMS v2 — Scored Test Report Runner")
    parser.add_argument(
        "--with-e2e",
        action="store_true",
        help="Run live E2E scenarios (requires LLM server). Adds 'Live E2E' category (weight 2.5).",
    )
    args = parser.parse_args()

    os.chdir(PROJECT_ROOT)

    results = []  # (label, weight, _ScoringResult)

    for label, module_name, weight in CATEGORIES:
        # Integration tests inject sys.modules mocks that can contaminate later tests
        cleanup = module_name == "tests.test_agent_server_integration"
        result = _run_category(module_name, cleanup_after=cleanup)
        results.append((label, weight, result))

    # Optionally run live E2E scenarios
    if args.with_e2e:
        print("\n--- Running Live E2E Scenarios ---\n")
        e2e_result = _run_e2e()
        results.append(("Live E2E", 2.5, e2e_result))

    report = _render_report(results)
    print(report)

    # Exit code
    total_passed = sum(r.passed for _, _, r in results)
    total_tests = sum(r.total for _, _, r in results)
    sys.exit(0 if total_passed == total_tests and total_tests > 0 else 1)


if __name__ == "__main__":
    main()
