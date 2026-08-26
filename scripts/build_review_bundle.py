#!/usr/bin/env python3
"""Build a bundle-first Reviewer context without restricting independent investigation."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from shutil import copyfile


TASK_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--attempt", default="1")
    parser.add_argument("--base-revision")
    parser.add_argument("--review-revision")
    parser.add_argument("--tests-json", type=Path)
    return parser.parse_args()


def run_git(root: Path, *git_args: str) -> tuple[str, int]:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *git_args],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return "", 127
    return completed.stdout, completed.returncode


def diff_args(args: argparse.Namespace) -> list[str]:
    if args.base_revision and args.review_revision:
        return [args.base_revision, args.review_revision]
    if args.base_revision:
        return [args.base_revision]
    if args.review_revision:
        return [args.review_revision]
    return []


def section(text: str, heading: str) -> str:
    match = re.search(rf"^## {re.escape(heading)}\s*$", text, re.MULTILINE)
    if not match:
        return ""
    tail = text[match.end():]
    next_heading = re.search(r"^##\s+", tail, re.MULTILINE)
    return tail[:next_heading.start()] if next_heading else tail


def expected_scope(task_text: str) -> list[str]:
    body = section(task_text, "Expected / Allowed Write Scope")
    values = []
    for line in body.splitlines():
        value = line.strip().lstrip("-* ").strip("`")
        if value and not value.startswith(("TODO", "...")):
            values.append(value)
    return sorted(set(values))


def in_scope(path: str, expected: list[str]) -> bool:
    return any(path == item or item.endswith("/") and path.startswith(item) for item in expected)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def main() -> int:
    args = parse_args()
    root = args.project_root.expanduser().resolve()
    if not TASK_ID_PATTERN.fullmatch(args.task_id):
        raise SystemExit("task-id must contain only letters, digits, dot, underscore, or hyphen")
    if not re.fullmatch(r"[1-9][0-9]*", args.attempt):
        raise SystemExit("attempt must be a positive integer")
    workflow = root / "Workflow"
    task_path = workflow / "tasks" / f"{args.task_id}.md"
    result_path = workflow / "results" / f"{args.task_id}.md"
    if not task_path.is_file():
        raise SystemExit(f"Task packet not found at {task_path}")
    if not result_path.is_file():
        raise SystemExit(f"Worker result not found at {result_path}")

    bundle = workflow / "review-bundles" / args.task_id / args.attempt
    if bundle.exists():
        raise SystemExit(f"Review bundle already exists at {bundle}; use a new --attempt instead of overwriting it")
    bundle.mkdir(parents=True, exist_ok=True)
    task_text = task_path.read_text(encoding="utf-8")
    expected = expected_scope(task_text)
    name_output, name_code = run_git(root, "diff", "--name-only", *diff_args(args))
    diff_output, diff_code = run_git(root, "diff", "--binary", *diff_args(args))
    changed_files = sorted({line.strip() for line in name_output.splitlines() if line.strip()})
    scope_violation = bool(expected) and any(not in_scope(path, expected) for path in changed_files)
    if name_code != 0:
        scope_signal = "WARNING"
        scope_note = "Git changed-file inspection was unavailable; Reviewer must inspect the actual diff."
    elif scope_violation:
        scope_signal = "BLOCKED"
        scope_note = "One or more changed files fall outside the expected write scope."
    elif not expected:
        scope_signal = "WARNING"
        scope_note = "Task packet did not provide a parseable expected write scope."
    else:
        scope_signal = "SAFE"
        scope_note = "Changed files are within the expected write scope."

    (bundle / "task-packet.md").write_text(task_text, encoding="utf-8")
    copyfile(result_path, bundle / "worker-result.md")
    (bundle / "changed-files.txt").write_text("\n".join(changed_files) + ("\n" if changed_files else ""), encoding="utf-8")
    (bundle / "diff.patch").write_text(diff_output if diff_code == 0 else "", encoding="utf-8")
    tests = {"commands": [], "note": "No test evidence file was supplied; Reviewer must perform targeted verification."}
    if args.tests_json:
        tests = json.loads(args.tests_json.read_text(encoding="utf-8"))
        if not isinstance(tests, dict):
            raise SystemExit("--tests-json must contain a JSON object")
    (bundle / "tests.json").write_text(json.dumps(tests, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    scope_check = {
        "signal": scope_signal,
        "note": scope_note,
        "actual_changed_files": changed_files,
        "expected_write_scope": expected,
        "scope_violation": scope_violation,
    }
    (bundle / "scope-check.json").write_text(json.dumps(scope_check, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    source_hashes = {
        "task_packet": sha256_file(task_path),
        "worker_result": sha256_file(result_path),
        "diff_patch": sha256_file(bundle / "diff.patch"),
    }
    for name in ("PLAN.md", "MAIN_BRIEF.md"):
        source_path = workflow / name
        if source_path.is_file():
            source_hashes[name] = sha256_file(source_path)
    metadata = {
        "task_id": args.task_id,
        "attempt": int(args.attempt),
        "created_at": timestamp(),
        "base_revision": args.base_revision,
        "review_revision": args.review_revision,
        "changed_files": changed_files,
        "expected_write_scope": expected,
        "scope_violation": scope_violation,
        "scope_signal": scope_signal,
        "source_hashes": source_hashes,
        "immutable": True,
    }
    (bundle / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (bundle / "review-context.md").write_text(
        "# Review Context\n\n"
        "Read `task-packet.md`, `worker-result.md`, `metadata.json`, `tests.json`, and `scope-check.json` first. "
        "This bundle is a high-quality starting context, not an information boundary: inspect any repository file, "
        "history, diff, or test needed to answer explicit review questions.\n\n"
        f"Guardrail signal: `{scope_signal}` — {scope_note}\n",
        encoding="utf-8",
    )
    print(f"built review bundle at {bundle}")
    return 1 if scope_signal == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
