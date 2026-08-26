#!/usr/bin/env python3
"""Record one runtime event and update the operational STATE without mutating MEMORY."""

from __future__ import annotations

import argparse
import fcntl
import json
import re
import uuid
from datetime import datetime
from pathlib import Path


TASK_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
VISIBLE_WORKFLOW_DIRNAME = "Workflow"
LEGACY_WORKFLOW_DIRNAME = ".workflow"


def timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--role", required=True, choices=("Chief", "Chef", "Main", "Worker", "Reviewer", "Expert Worker", "Escalation"))
    parser.add_argument("--action", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--event-type", choices=(
        "workflow_initialized", "task_created", "task_started", "worker_dispatched",
        "worker_completed", "review_started", "review_completed", "review_passed",
        "review_failed", "expert_worker_dispatched", "repair_created", "decision_recorded",
        "state_changed", "task_closed", "task_blocked", "blocked", "workflow_closed", "note",
    ))
    parser.add_argument("--evidence", default="none")
    parser.add_argument("--next-action", default="none")
    parser.add_argument("--status")
    parser.add_argument("--timestamp", dest="event_timestamp")
    parser.add_argument("--event-id")
    parser.add_argument("--idempotency-key")
    parser.add_argument("--attempt", type=int, default=1)
    return parser.parse_args()


def infer_event_type(args: argparse.Namespace) -> str:
    text = f"{args.action} {args.result}".lower()
    if "review" in text and "fail" in text:
        return "review_failed"
    if "review" in text and "pass" in text:
        return "review_passed"
    if "review" in text and ("start" in text or "dispatch" in text):
        return "review_started"
    if "expert" in text and "dispatch" in text:
        return "expert_worker_dispatched"
    if "worker" in text and "dispatch" in text:
        return "worker_dispatched"
    if "worker" in text and ("complete" in text or "done" in text):
        return "worker_completed"
    if "block" in text:
        return "task_blocked"
    if "close" in text or "pass" in text:
        return "task_closed"
    return "note"


def load_json_object(path: Path, default: dict) -> dict:
    if not path.exists():
        return default
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"{path} must contain a JSON object")
    return value


def status_for_event(event_type: str) -> str | None:
    return {
        "task_started": "EXECUTING",
        "worker_dispatched": "EXECUTING",
        "worker_completed": "REVIEWING",
        "review_started": "REVIEWING",
        "review_passed": "PASSED",
        "review_failed": "REPAIRING",
        "expert_worker_dispatched": "REPAIRING",
        "task_closed": "PASSED",
        "task_blocked": "BLOCKED",
        "blocked": "BLOCKED",
    }.get(event_type)


def update_state(state_path: Path, args: argparse.Namespace, event_type: str, event_time: str) -> None:
    state = load_json_object(
        state_path,
        {
            "workflow": "chef-worker-reviewer-workflow",
            "version": "1.4",
            "workflow_status": "READY",
            "tasks": {},
            "active_agent_jobs": [],
            "blockers": [],
        },
    )
    tasks = state.setdefault("tasks", {})
    if not isinstance(tasks, dict):
        raise SystemExit(f"{state_path}.tasks must be an object")
    task = tasks.setdefault(args.task_id, {
        "status": "READY",
        "worker_attempts": 0,
        "review_attempts": 0,
        "worker_failures": 0,
        "expert_worker_required": False,
    })
    if not isinstance(task, dict):
        raise SystemExit(f"{state_path}.tasks.{args.task_id} must be an object")
    task.setdefault("worker_attempts", 0)
    task.setdefault("review_attempts", 0)
    task.setdefault("worker_failures", 0)
    if event_type in ("worker_dispatched", "expert_worker_dispatched"):
        task["worker_attempts"] += 1
    elif event_type == "review_started":
        task["review_attempts"] += 1
    elif event_type == "review_failed":
        task["worker_failures"] += 1
        task["expert_worker_required"] = task["worker_failures"] >= 2
    elif event_type == "review_passed":
        task["expert_worker_required"] = False
    event_status = args.status or status_for_event(event_type)
    if event_status:
        task["status"] = event_status
        state["workflow_status"] = event_status
    task["latest_runtime_update"] = event_time
    state["latest_runtime_update"] = event_time
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    project_root = args.project_root.expanduser().resolve()
    if not TASK_ID_PATTERN.fullmatch(args.task_id):
        raise SystemExit("task-id must contain only letters, digits, dot, underscore, or hyphen")

    workflow_root = project_root / VISIBLE_WORKFLOW_DIRNAME
    legacy_root = project_root / LEGACY_WORKFLOW_DIRNAME
    if workflow_root.exists() and legacy_root.exists():
        raise SystemExit(
            f"Both {workflow_root} and legacy {legacy_root} exist; resolve the duplicate workflow roots before recording events"
        )
    if not workflow_root.is_dir() and legacy_root.exists():
        raise SystemExit(
            f"Legacy hidden workflow directory detected at {legacy_root}; "
            "migrate it with init_project_workflow.py --migrate-legacy first"
        )
    task_packet = workflow_root / "tasks" / f"{args.task_id}.md"
    if not task_packet.is_file():
        raise SystemExit(f"Task packet not found at {task_packet}; create it before recording an event")

    memory_path = project_root / "MEMORY.md"
    if not memory_path.is_file():
        raise SystemExit(f"MEMORY.md not found at {memory_path}; initialize the workflow first")

    event_time = args.event_timestamp or timestamp()
    event_type = args.event_type or infer_event_type(args)
    event = {
        "event_id": args.event_id or str(uuid.uuid4()),
        "idempotency_key": args.idempotency_key,
        "attempt": args.attempt,
        "timestamp": event_time,
        "event_type": event_type,
        "task_id": args.task_id,
        "role": "Chief" if args.role == "Chef" else args.role,
        "action": args.action,
        "result": args.result,
        "evidence": args.evidence,
        "next_action": args.next_action,
    }
    events_path = workflow_root / "events.jsonl"
    lock_path = workflow_root / "events.jsonl.lock"
    with lock_path.open("a", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        existing_event_ids = set()
        existing_idempotency_keys = set()
        if events_path.exists():
            for line in events_path.read_text(encoding="utf-8").splitlines():
                try:
                    previous = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(previous, dict):
                    if previous.get("event_id"):
                        existing_event_ids.add(previous["event_id"])
                    if previous.get("idempotency_key"):
                        existing_idempotency_keys.add(previous["idempotency_key"])
        if event["event_id"] in existing_event_ids or event["idempotency_key"] in existing_idempotency_keys:
            print(f"duplicate runtime event ignored in {events_path}")
            return 0
        event["sequence"] = len(events_path.read_text(encoding="utf-8").splitlines()) + 1 if events_path.exists() else 1
        with events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        update_state(workflow_root / "STATE.json", args, event_type, event_time)
        fcntl.flock(lock, fcntl.LOCK_UN)
    print(f"recorded runtime event in {events_path}")
    print(f"updated operational state in {workflow_root / 'STATE.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
