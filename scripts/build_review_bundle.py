#!/usr/bin/env python3
"""Build a bundle-first Reviewer context without restricting independent investigation."""

from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import re
import stat
import subprocess
from datetime import datetime
from pathlib import Path
from shutil import copyfile


TASK_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
ACTIVE_TASK_STATUSES = {"EXECUTING", "REVIEWING", "REPAIRING", "ACTIVE"}


def timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--attempt", default="1")
    parser.add_argument("--base-revision")
    parser.add_argument("--review-revision")
    parser.add_argument("--task-patch", type=Path, help="Use a task-specific saved patch instead of reading the working tree")
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


def normalize_scope_path(value: str) -> str:
    return posixpath.normpath(value.strip().strip("`"))


def path_within_scope(path: str, scope: str) -> bool:
    normalized_path = normalize_scope_path(path)
    normalized_scope = normalize_scope_path(scope)
    return normalized_path == normalized_scope or normalized_path.startswith(normalized_scope.rstrip("/") + "/")


def in_scope(path: str, expected: list[str]) -> bool:
    return any(path_within_scope(path, item) for item in expected)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_state(workflow: Path) -> dict:
    state_path = workflow / "STATE.json"
    if not state_path.is_file():
        return {}
    try:
        value = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def active_other_tasks(workflow: Path, task_id: str) -> list[str]:
    state = load_state(workflow)
    active = {
        task_key
        for task_key, task in state.get("tasks", {}).items()
        if task_key != task_id and isinstance(task, dict) and task.get("status") in ACTIVE_TASK_STATUSES
    }
    for job in state.get("active_agent_jobs", []):
        if isinstance(job, dict) and job.get("task_id") != task_id and job.get("role") in {"Worker", "Expert Worker"}:
            if job.get("task_id"):
                active.add(str(job["task_id"]))
    return sorted(active)


def patch_changed_files(patch: str) -> list[str]:
    changed = set()
    for line in patch.splitlines():
        if not line.startswith("diff --git "):
            continue
        parts = line.split()
        if len(parts) >= 4:
            for value in parts[2:4]:
                changed.add(value[2:] if value.startswith(("a/", "b/")) else value)
    return sorted(changed)


def make_snapshot_read_only(paths: list[Path]) -> None:
    for path in paths:
        mode = path.stat().st_mode
        path.chmod(mode & ~stat.S_IWUSR & ~stat.S_IWGRP & ~stat.S_IWOTH)


def main() -> int:
    args = parse_args()
    root = args.project_root.expanduser().resolve()
    if not TASK_ID_PATTERN.fullmatch(args.task_id):
        raise SystemExit("task-id must contain only letters, digits, dot, underscore, or hyphen")
    if not re.fullmatch(r"[1-9][0-9]*", args.attempt):
        raise SystemExit("attempt must be a positive integer")
    if bool(args.base_revision) != bool(args.review_revision):
        raise SystemExit("--base-revision and --review-revision must be supplied together")
    if args.task_patch and (args.base_revision or args.review_revision):
        raise SystemExit("--task-patch cannot be combined with revision boundaries")
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
    task_text = task_path.read_text(encoding="utf-8")
    expected = expected_scope(task_text)
    other_active_tasks = active_other_tasks(workflow, args.task_id)
    status_output, status_code = run_git(root, "status", "--porcelain", "--untracked-files=all")
    working_tree_dirty = bool(status_output.strip())

    diff_source = "working_tree_fallback"
    stability_signal = "WARNING"
    stability_note = "Working-tree fallback is allowed only because no other active Worker task is recorded."
    if args.task_patch:
        if not args.task_patch.is_file():
            raise SystemExit(f"Task-specific patch not found at {args.task_patch}")
        diff_output = args.task_patch.read_text(encoding="utf-8")
        changed_files = patch_changed_files(diff_output)
        diff_code = 0
        diff_source = "task_specific_patch"
        stability_signal = "SAFE"
        stability_note = "A task-specific saved patch is the review evidence boundary."
    elif args.base_revision and args.review_revision:
        name_output, name_code = run_git(root, "diff", "--name-only", args.base_revision, args.review_revision)
        diff_output, diff_code = run_git(root, "diff", "--binary", args.base_revision, args.review_revision)
        if name_code != 0 or diff_code != 0:
            raise SystemExit("Stable revision boundary could not be read; do not build a review bundle from an unknown diff")
        changed_files = sorted({line.strip() for line in name_output.splitlines() if line.strip()})
        diff_source = "revision_boundary"
        stability_signal = "SAFE"
        stability_note = "The bundle uses the explicit base-revision to review-revision diff."
    else:
        diff_output, diff_code = run_git(root, "diff", "--binary")
        name_output, name_code = run_git(root, "diff", "--name-only")
        changed_files = sorted({line.strip() for line in name_output.splitlines() if line.strip()})
        if other_active_tasks:
            print(
                "UNSTABLE_REVIEW_DIFF: shared dirty worktree has active other tasks "
                f"{', '.join(other_active_tasks)}; provide revisions, a task-specific patch, or wait",
            )
            return 1
        if status_code != 0 or name_code != 0 or diff_code != 0:
            stability_note = "Git working-tree inspection was unavailable; Reviewer must inspect the actual diff."
        elif not working_tree_dirty:
            stability_note = "No working-tree changes were detected; Reviewer must verify the revision/evidence boundary."

    scope_violation = bool(expected) and any(not in_scope(path, expected) for path in changed_files)
    if scope_violation:
        scope_signal = "BLOCKED"
        scope_note = "One or more changed files fall outside the expected write scope."
    elif not expected:
        scope_signal = "WARNING"
        scope_note = "Task packet did not provide a parseable expected write scope."
    else:
        scope_signal = "SAFE"
        scope_note = "Changed files are within the expected write scope."

    bundle.mkdir(parents=True, exist_ok=True)
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
        "diff_source": diff_source,
        "stability_signal": stability_signal,
        "stability_note": stability_note,
        "active_other_tasks": other_active_tasks,
        "working_tree_dirty": working_tree_dirty,
        "changed_files": changed_files,
        "expected_write_scope": expected,
        "scope_violation": scope_violation,
        "scope_signal": scope_signal,
        "source_hashes": source_hashes,
        "immutable": True,
        "immutable_meaning": "Generated bundle files are read-only snapshots; the underlying repository may change.",
    }
    (bundle / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (bundle / "review-context.md").write_text(
        "# Review Context\n\n"
        "Read `task-packet.md`, `worker-result.md`, `metadata.json`, `tests.json`, and `scope-check.json` first. "
        "This bundle is a high-quality starting context, not an information boundary: inspect any repository file, "
        "history, diff, or test needed to answer explicit review questions.\n\n"
        f"Diff source: `{diff_source}`; stability: `{stability_signal}` — {stability_note}\n"
        f"Guardrail signal: `{scope_signal}` — {scope_note}\n",
        encoding="utf-8",
    )
    make_snapshot_read_only([path for path in bundle.iterdir() if path.is_file()])
    print(f"built review bundle at {bundle}")
    return 1 if scope_signal == "BLOCKED" or stability_signal == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
