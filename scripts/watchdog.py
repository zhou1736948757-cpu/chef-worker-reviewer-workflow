#!/usr/bin/env python3
"""Monitor visible Workflow heartbeats and report suspected agent/provider stalls to Main."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path


VISIBLE_WORKFLOW_DIRNAME = "Workflow"
LEGACY_WORKFLOW_DIRNAME = ".workflow"
DEFAULT_INTERVAL_SECONDS = 600
ROLE_NAMES = ("Main", "Chief", "Worker", "Reviewer", "Expert Worker")
ACTIVE_TASK_STATUSES = {"EXECUTING", "REVIEWING", "REPAIRING", "ACTIVE"}


def timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--start", action="store_true", help="Create the visible Watchdog records and monitor")
    parser.add_argument("--background", action="store_true", help="With --start, keep monitoring in a detached process")
    parser.add_argument("--run", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--once", action="store_true", help="Check once and report to Main")
    parser.add_argument("--heartbeat", action="store_true", help="Record one role heartbeat")
    parser.add_argument("--role", choices=ROLE_NAMES)
    parser.add_argument("--task-id")
    parser.add_argument("--status", choices=("ACTIVE", "IDLE", "BLOCKED", "DONE"), default="ACTIVE")
    parser.add_argument("--interval-seconds", type=int, default=DEFAULT_INTERVAL_SECONDS)
    parser.add_argument("--stale-after-seconds", type=int)
    return parser.parse_args()


def require_visible_workflow(root: Path) -> Path:
    workflow = root / VISIBLE_WORKFLOW_DIRNAME
    legacy = root / LEGACY_WORKFLOW_DIRNAME
    if not workflow.is_dir():
        if legacy.exists():
            raise SystemExit(
                f"Legacy hidden workflow directory detected at {legacy}; "
                "migrate it to visible Workflow/ before starting Watchdog"
            )
        raise SystemExit(f"Visible workflow directory not found at {workflow}; initialize the workflow first")
    return workflow


def read_json(path: Path, default: dict) -> dict:
    if not path.is_file():
        return default
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"{path} must contain a JSON object")
    return value


def atomic_write_json(path: Path, value: dict) -> None:
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix=f"{path.name}.tmp-", delete=False
    ) as handle:
        temporary = Path(handle.name)
        handle.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    os.replace(temporary, path)


def lock_path(workflow: Path) -> Path:
    return workflow / "watchdog.lock"


def with_lock(workflow: Path):
    handle = lock_path(workflow).open("a", encoding="utf-8")
    fcntl.flock(handle, fcntl.LOCK_EX)
    return handle


def release_lock(handle) -> None:
    fcntl.flock(handle, fcntl.LOCK_UN)
    handle.close()


def update_heartbeat(workflow: Path, role: str, task_id: str | None, status: str) -> None:
    heartbeat_path = workflow / "heartbeats.json"
    lock = with_lock(workflow)
    try:
        heartbeats = read_json(heartbeat_path, {})
        heartbeats[role] = {
            "role": role,
            "task_id": task_id,
            "status": status,
            "last_heartbeat": timestamp(),
        }
        atomic_write_json(heartbeat_path, heartbeats)
    finally:
        release_lock(lock)


def parse_timestamp(value: object) -> float | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def stale_age(value: object, now: float) -> int | None:
    parsed = parse_timestamp(value)
    if parsed is None:
        return None
    return max(0, int(now - parsed))


def recent_task_roles(workflow: Path) -> dict[str, str]:
    roles = {}
    events_path = workflow / "events.jsonl"
    if not events_path.is_file():
        return roles
    for line in events_path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("task_id") and event.get("role"):
            roles[str(event["task_id"])] = str(event["role"])
    return roles


def candidates(workflow: Path, stale_after: int, now: float) -> list[dict]:
    alerts = []
    state = read_json(workflow / "STATE.json", {})
    tasks = state.get("tasks", {})
    active_task_ids = {
        str(task_id)
        for task_id, task in tasks.items()
        if isinstance(task, dict) and task.get("status") in ACTIVE_TASK_STATUSES
    } if isinstance(tasks, dict) else set()
    workflow_active = state.get("workflow_status") in ACTIVE_TASK_STATUSES
    heartbeats = read_json(workflow / "heartbeats.json", {})
    for role, heartbeat in heartbeats.items():
        if not isinstance(heartbeat, dict) or heartbeat.get("status") != "ACTIVE":
            continue
        task_id = heartbeat.get("task_id")
        # A heartbeat tied to a completed task is no longer evidence of a
        # live stall. An unassigned Main heartbeat is relevant only while the
        # workflow has active work; planning heartbeats may use a synthetic
        # task id and remain observable.
        relevant = (
            (str(task_id) in active_task_ids or str(task_id) not in tasks)
            if task_id is not None
            else workflow_active
        )
        if not relevant:
            continue
        age = stale_age(heartbeat.get("last_heartbeat"), now)
        if age is not None and age >= stale_after:
            alerts.append({
                "kind": "stale_heartbeat",
                "suspected_role": role,
                "task_id": task_id,
                "age_seconds": age,
                "reason": "possible network, provider, or unresponsive-agent stall",
                "evidence": f"{role} heartbeat is older than {stale_after} seconds",
            })
    task_roles = recent_task_roles(workflow)
    if isinstance(tasks, dict):
        for task_id, task in tasks.items():
            if not isinstance(task, dict) or task.get("status") not in ACTIVE_TASK_STATUSES:
                continue
            age = stale_age(task.get("latest_runtime_update"), now)
            if age is not None and age >= stale_after:
                alerts.append({
                    "kind": "stale_task_runtime",
                    "suspected_role": task_roles.get(str(task_id), "Main"),
                    "task_id": task_id,
                    "age_seconds": age,
                    "reason": "possible network, provider, or unresponsive-agent stall",
                    "evidence": f"task status is {task.get('status')} without a runtime update for {age} seconds",
                })
    return alerts


def fingerprint(alert: dict) -> str:
    return json.dumps(
        {key: alert.get(key) for key in ("kind", "suspected_role", "task_id")},
        sort_keys=True,
        ensure_ascii=False,
    )


def append_alert(workflow: Path, alert: dict) -> None:
    alert_path = workflow / "watchdog-alerts.jsonl"
    event_path = workflow / "events.jsonl"
    event_time = timestamp()
    alert_record = {"alert_id": str(uuid.uuid4()), "timestamp": event_time, **alert}
    event_record = {
        "event_id": str(uuid.uuid4()),
        "timestamp": event_time,
        "event_type": "watchdog_alert",
        "task_id": alert.get("task_id") or "WORKFLOW",
        "role": "Watchdog",
        "action": "report suspected stall to Main",
        "result": alert["reason"],
        "evidence": alert["evidence"],
        "next_action": "Main should inspect the affected agent/provider and decide whether to retry, serialize, or escalate",
    }
    lock = with_lock(workflow)
    try:
        with alert_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(alert_record, ensure_ascii=False) + "\n")
        with event_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event_record, ensure_ascii=False) + "\n")
    finally:
        release_lock(lock)
    print(json.dumps(alert_record, ensure_ascii=False))


def check_once(workflow: Path, interval: int, stale_after: int) -> int:
    now = time.time()
    config_path = workflow / "watchdog.json"
    config = read_json(config_path, {})
    config.update({
        "enabled": True,
        "interval_seconds": interval,
        "stale_after_seconds": stale_after,
        "last_check_at": timestamp(),
        "main_report_target": "Main current conversation",
    })
    open_alerts = config.get("open_alerts", {})
    if not isinstance(open_alerts, dict):
        open_alerts = {}
    found = candidates(workflow, stale_after, now)
    found_fingerprints = {fingerprint(alert) for alert in found}
    emitted = []
    for alert in found:
        key = fingerprint(alert)
        if key not in open_alerts:
            append_alert(workflow, alert)
            emitted.append(alert)
            open_alerts[key] = timestamp()
    config["open_alerts"] = {key: value for key, value in open_alerts.items() if key in found_fingerprints}
    lock = with_lock(workflow)
    try:
        atomic_write_json(config_path, config)
    finally:
        release_lock(lock)
    if not emitted:
        print(json.dumps({"status": "OK", "checked_at": config["last_check_at"], "alerts": []}, ensure_ascii=False))
    return 1 if emitted else 0


def pid_is_alive(pid: object) -> bool:
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def start(workflow: Path, interval: int, stale_after: int, background: bool) -> int:
    config_path = workflow / "watchdog.json"
    config = read_json(config_path, {})
    existing_pid = config.get("pid")
    if background and pid_is_alive(existing_pid):
        print(f"Watchdog already running with pid {existing_pid}; reporting to Main via Workflow/watchdog-alerts.jsonl")
        return 0
    update_heartbeat(workflow, "Main", None, "ACTIVE")
    config.update({
        "enabled": True,
        "interval_seconds": interval,
        "stale_after_seconds": stale_after,
        "started_at": config.get("started_at") or timestamp(),
        "main_report_target": "Main current conversation",
    })
    if background:
        command = [
            sys.executable, str(Path(__file__).resolve()),
            "--project-root", str(workflow.parent), "--run",
            "--interval-seconds", str(interval), "--stale-after-seconds", str(stale_after),
        ]
        child = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        config["pid"] = child.pid
        atomic_write_json(config_path, config)
        print(f"started visible Workflow Watchdog in background with pid {child.pid}")
        return 0
    config["pid"] = os.getpid()
    atomic_write_json(config_path, config)
    try:
        while True:
            check_once(workflow, interval, stale_after)
            time.sleep(interval)
    except KeyboardInterrupt:
        config = read_json(config_path, config)
        config["enabled"] = False
        config["pid"] = None
        atomic_write_json(config_path, config)
        return 0


def run() -> int:
    args = parse_args()
    if args.interval_seconds < 1:
        raise SystemExit("--interval-seconds must be positive")
    stale_after = args.stale_after_seconds or args.interval_seconds
    if stale_after < 1:
        raise SystemExit("--stale-after-seconds must be positive")
    root = args.project_root.expanduser().resolve()
    workflow = require_visible_workflow(root)
    if args.heartbeat:
        if not args.role:
            raise SystemExit("--heartbeat requires --role")
        update_heartbeat(workflow, args.role, args.task_id, args.status)
        print(f"recorded {args.role} heartbeat in {workflow / 'heartbeats.json'}")
        return 0
    if args.start:
        return start(workflow, args.interval_seconds, stale_after, args.background)
    if args.run:
        while True:
            check_once(workflow, args.interval_seconds, stale_after)
            time.sleep(args.interval_seconds)
    return check_once(workflow, args.interval_seconds, stale_after)


if __name__ == "__main__":
    raise SystemExit(run())
