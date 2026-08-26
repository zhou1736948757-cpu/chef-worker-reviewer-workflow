#!/usr/bin/env python3
"""Validate compact test evidence and reject zero-test false positives."""

from __future__ import annotations

import argparse
import json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exit-code", required=True, type=int)
    parser.add_argument("--executed-tests", required=True, type=int)
    parser.add_argument("--passed-tests", type=int, default=0)
    parser.add_argument("--failed-tests", type=int, default=0)
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    errors = []
    if args.executed_tests < 0 or args.passed_tests < 0 or args.failed_tests < 0:
        errors.append("test counts must be non-negative")
    if args.passed_tests + args.failed_tests > args.executed_tests:
        errors.append("passed-tests plus failed-tests cannot exceed executed-tests")
    if args.exit_code == 0 and args.executed_tests == 0:
        errors.append("exit code 0 with zero executed tests is INVALID_TEST_EXECUTION")
    if args.exit_code != 0:
        errors.append(f"test command exited with code {args.exit_code}")
    if args.failed_tests:
        errors.append(f"{args.failed_tests} test(s) failed")
    result = {
        "valid": not errors,
        "status": "VALID_TEST_EVIDENCE" if not errors else "INVALID_TEST_EXECUTION",
        "exit_code": args.exit_code,
        "executed_tests": args.executed_tests,
        "passed_tests": args.passed_tests,
        "failed_tests": args.failed_tests,
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.as_json else result["status"])
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
