#!/usr/bin/env python3
"""Append one concise, structured event to the project workflow memory."""

from __future__ import annotations

import argparse
import re
from datetime import datetime
from pathlib import Path


WORKLOG_START = "<!-- chef-worker-reviewer-workflow:work-log:start -->"
WORKLOG_END = "<!-- chef-worker-reviewer-workflow:work-log:end -->"
TASK_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
VISIBLE_WORKFLOW_DIRNAME = "Workflow"
LEGACY_WORKFLOW_DIRNAME = ".workflow"


def timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--role", required=True, choices=("Chief", "Chef", "Worker", "Reviewer", "Escalation"))
    parser.add_argument("--action", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--evidence", default="none")
    parser.add_argument("--next-action", default="none")
    parser.add_argument("--timestamp", dest="event_timestamp")
    return parser.parse_args()


def build_entry(args: argparse.Namespace) -> str:
    event_time = args.event_timestamp or timestamp()
    role = "Chief" if args.role == "Chef" else args.role
    return "\n".join(
        [
            f"### {event_time} — {args.task_id}",
            f"- Role: `{role}`",
            f"- Action: {args.action}",
            f"- Result: {args.result}",
            f"- Evidence: `{args.evidence}`",
            f"- Next: {args.next_action}",
            "",
        ]
    )


def append_entry(content: str, entry: str) -> str:
    if WORKLOG_START in content and WORKLOG_END in content:
        start = content.index(WORKLOG_START) + len(WORKLOG_START)
        end = content.index(WORKLOG_END, start)
        body = content[start:end]
        body = body.replace("\nNo workflow events recorded yet.\n", "\n")
        return content[:start] + body.rstrip() + "\n\n" + entry + content[end:]

    heading = "### Work log"
    if heading in content:
        return content.rstrip() + "\n\n" + entry
    return content.rstrip() + "\n\n## Work log\n\n" + entry


def main() -> int:
    args = parse_args()
    project_root = args.project_root.expanduser().resolve()
    if not TASK_ID_PATTERN.fullmatch(args.task_id):
        raise SystemExit("task-id must contain only letters, digits, dot, underscore, or hyphen")

    workflow_root = project_root / VISIBLE_WORKFLOW_DIRNAME
    if not workflow_root.is_dir() and (project_root / LEGACY_WORKFLOW_DIRNAME).exists():
        raise SystemExit(
            f"Legacy hidden workflow directory detected at {project_root / LEGACY_WORKFLOW_DIRNAME}; "
            "migrate it with init_project_workflow.py --migrate-legacy first"
        )

    task_packet = workflow_root / "tasks" / f"{args.task_id}.md"
    if not task_packet.is_file():
        raise SystemExit(f"Task packet not found at {task_packet}; create it before recording an event")

    memory_path = project_root / "MEMORY.md"
    if not memory_path.is_file():
        raise SystemExit(f"MEMORY.md not found at {memory_path}; initialize the workflow first")

    existing = memory_path.read_text(encoding="utf-8")
    if args.task_id in existing and args.action in existing:
        raise SystemExit("A matching task/action entry already exists; refusing to duplicate it")

    memory_path.write_text(append_entry(existing, build_entry(args)), encoding="utf-8")
    print(f"recorded workflow event in {memory_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
