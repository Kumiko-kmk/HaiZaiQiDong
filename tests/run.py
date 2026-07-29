"""Unified test runner.

Usage:
    python -m tests.run
    python -m tests.run unit
    python -m tests.run integration
"""

from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_ROOT = Path(__file__).resolve().parent
INTEGRATION_ROOT = TEST_ROOT / "integration"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _discover(start_dir: Path) -> unittest.TestSuite:
    return unittest.defaultTestLoader.discover(
        str(start_dir),
        pattern="test_*.py",
        top_level_dir=str(PROJECT_ROOT),
    )


def _without_integration(suite: unittest.TestSuite) -> unittest.TestSuite:
    filtered = unittest.TestSuite()
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            nested = _without_integration(item)
            if nested.countTestCases():
                filtered.addTest(nested)
        elif ".integration." not in item.id():
            filtered.addTest(item)
    return filtered


def build_suite(scope: str) -> unittest.TestSuite:
    if scope == "integration":
        return _discover(INTEGRATION_ROOT)
    suite = _discover(TEST_ROOT)
    return _without_integration(suite) if scope == "unit" else suite


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run HaiZaiQiDong tests")
    parser.add_argument(
        "scope",
        choices=("all", "unit", "integration"),
        default="all",
        nargs="?",
    )
    parser.add_argument("-q", "--quiet", action="store_true")
    args = parser.parse_args(argv)
    result = unittest.TextTestRunner(verbosity=1 if args.quiet else 2).run(
        build_suite(args.scope)
    )
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
