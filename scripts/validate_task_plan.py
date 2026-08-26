#!/usr/bin/env python3
"""Emit deterministic plan guardrail signals without scheduling agents."""

from __future__ import annotations

import argparse
import json
import posixpath
import re
from pathlib import Path


TASK_ID = re.compile(r"T-[A-Za-z0-9][A-Za-z0-9._-]*")
HEADINGS = ("Objective", "Dependencies", "Scope", "Acceptance Criteria", "Required Verification")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--task-id")
    parser.add_argument("--completed-task", action="append", default=[])
    parser.add_argument("--reviewing-task")
    parser.add_argument("--candidate-task")
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser.parse_args()


def task_ids(text: str) -> list[str]:
    return sorted(set(TASK_ID.findall(text)))


def section(text: str, heading: str) -> str:
    match = re.search(rf"^## {re.escape(heading)}\s*$", text, re.MULTILINE)
    if not match:
        return ""
    tail = text[match.end():]
    next_heading = re.search(r"^##\s+", tail, re.MULTILINE)
    return tail[:next_heading.start()] if next_heading else tail


def write_scope(text: str) -> set[str]:
    body = section(text, "Expected / Allowed Write Scope")
    paths = set()
    for line in body.splitlines():
        stripped = line.strip().lstrip("-* ")
        if stripped and not stripped.startswith("TODO") and not stripped.startswith("..."):
            normalized = posixpath.normpath(stripped.strip("`"))
            paths.add(normalized)
    return paths


def paths_overlap(left: str, right: str) -> bool:
    if left == right:
        return True
    left_prefix = left.rstrip("/") + "/"
    right_prefix = right.rstrip("/") + "/"
    return left.startswith(right_prefix) or right.startswith(left_prefix)


def dependency_map(plan_text: str, task_texts: dict[str, str]) -> dict[str, set[str]]:
    graph = {task_id: set() for task_id in task_texts}
    for match in re.finditer(r"(T-[A-Za-z0-9][A-Za-z0-9._-]*)\s+depends on\s+((?:T-[A-Za-z0-9][A-Za-z0-9._-]*[ ,]*)+)", plan_text, re.IGNORECASE):
        graph.setdefault(match.group(1), set()).update(task_ids(match.group(2)))
    for task_id, text in task_texts.items():
        graph[task_id].update(task_ids(section(text, "Dependencies")))
    return graph


def has_cycle(graph: dict[str, set[str]]) -> bool:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        if any(visit(dep) for dep in graph.get(node, ())):
            return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(visit(node) for node in graph)


def main() -> int:
    args = parse_args()
    root = args.project_root.expanduser().resolve()
    workflow = root / "Workflow"
    task_dir = workflow / "tasks"
    issues: list[dict] = []
    signals: list[str] = []
    task_texts = {path.stem: path.read_text(encoding="utf-8") for path in sorted(task_dir.glob("*.md"))} if task_dir.is_dir() else {}
    plan_path = workflow / "PLAN.md"
    plan_text = plan_path.read_text(encoding="utf-8") if plan_path.is_file() else ""

    if not plan_text:
        issues.append({"severity": "BLOCKED", "code": "missing_plan", "message": "Workflow/PLAN.md is missing"})
    if not task_texts:
        issues.append({"severity": "WARNING", "code": "no_tasks", "message": "No task packets found"})

    known_ids = set(task_texts)
    graph = dependency_map(plan_text, task_texts)
    for task_id, text in task_texts.items():
        for heading in HEADINGS:
            if not section(text, heading).strip():
                issues.append({"severity": "WARNING", "code": "missing_field", "task_id": task_id, "field": heading})
        for dep in graph.get(task_id, ()):
            if dep not in known_ids:
                issues.append({"severity": "BLOCKED", "code": "unknown_dependency", "task_id": task_id, "dependency": dep})
    if has_cycle(graph):
        issues.append({"severity": "BLOCKED", "code": "dependency_cycle", "message": "Task dependency graph contains a cycle"})

    scopes = {task_id: write_scope(text) for task_id, text in task_texts.items()}
    for left, left_scope in scopes.items():
        for right, right_scope in scopes.items():
            if left >= right:
                continue
            overlap = sorted({left_path for left_path in left_scope for right_path in right_scope if paths_overlap(left_path, right_path)})
            if overlap:
                issues.append({"severity": "WARNING", "code": "shared_write_scope", "tasks": [left, right], "paths": overlap})

    if args.task_id:
        if args.task_id not in graph:
            issues.append({"severity": "BLOCKED", "code": "unknown_task", "task_id": args.task_id})
        else:
            missing = sorted(graph[args.task_id] - set(args.completed_task))
            if missing:
                issues.append({"severity": "BLOCKED", "code": "dependency_not_ready", "task_id": args.task_id, "missing": missing})
            else:
                signals.append("SAFE")

    if args.reviewing_task and args.candidate_task:
        overlap = sorted({left_path for left_path in scopes.get(args.reviewing_task, set()) for right_path in scopes.get(args.candidate_task, set()) if paths_overlap(left_path, right_path)})
        if overlap:
            issues.append({"severity": "BLOCKED", "code": "review_stability_conflict", "tasks": [args.reviewing_task, args.candidate_task], "paths": overlap})
        else:
            signals.append("SAFE")

    if any(issue["severity"] == "BLOCKED" for issue in issues):
        signals.append("BLOCKED")
    elif any(issue["severity"] == "WARNING" for issue in issues):
        signals.append("WARNING")
    elif not signals:
        signals.append("SAFE")
    result = {"signals": sorted(set(signals), key=("SAFE", "WARNING", "BLOCKED").index), "issues": issues, "task_count": len(task_texts), "dependencies": {key: sorted(value) for key, value in graph.items()}}
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.as_json else "\n".join(result["signals"]))
    return 0 if "BLOCKED" not in result["signals"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
