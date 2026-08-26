#!/usr/bin/env python3
"""Safely initialize the project-local Chief/Worker/Reviewer workflow."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
AGENTS_TEMPLATE = SKILL_ROOT / "references" / "AGENTS.template.md"
MEMORY_TEMPLATE = SKILL_ROOT / "references" / "MEMORY.template.md"

AGENTS_START = "<!-- chef-worker-reviewer-workflow:start -->"
AGENTS_END = "<!-- chef-worker-reviewer-workflow:end -->"
MEMORY_START = "<!-- chef-worker-reviewer-workflow:memory:start -->"
MEMORY_RUNTIME_START = "<!-- chef-worker-reviewer-workflow:runtime-config:start -->"
MEMORY_RUNTIME_END = "<!-- chef-worker-reviewer-workflow:runtime-config:end -->"

THINKING_DEPTHS = ("none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra")
FILE_POLICIES = ("merge", "overwrite")
VISIBLE_WORKFLOW_DIRNAME = "Workflow"
LEGACY_WORKFLOW_DIRNAME = ".workflow"
WORKFLOW_VERSION = "1.4"
CONFIG_ARG_NAMES = (
    "chef_model",
    "worker_model",
    "reviewer_model",
    "max_worker_concurrency",
    "thinking_depth",
)


def timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def render(template: str, values: dict[str, str]) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    return rendered.strip() + "\n"


def validate_runtime_config(config: dict) -> dict:
    if config.get("workflow") != "chef-worker-reviewer-workflow":
        raise SystemExit("Workflow/config.json has an unexpected workflow name")

    models = config.get("models")
    if not isinstance(models, dict):
        raise SystemExit("Workflow/config.json must contain a models object")
    for role in ("chief", "worker", "reviewer"):
        model = models.get(role)
        if not isinstance(model, str) or not model.strip():
            raise SystemExit(f"Workflow/config.json must contain a non-empty {role} model")
        models[role] = model.strip()
    main_model = models.get("main")
    if main_model is not None:
        if not isinstance(main_model, str) or not main_model.strip():
            raise SystemExit("Workflow/config.json main model must be a non-empty string or null")
        models["main"] = main_model.strip()

    concurrency = config.get("max_worker_concurrency")
    if isinstance(concurrency, bool) or not isinstance(concurrency, int) or concurrency < 1:
        raise SystemExit("max_worker_concurrency must be a positive integer")

    thinking_depth = config.get("thinking_depth")
    if thinking_depth not in THINKING_DEPTHS:
        choices = ", ".join(THINKING_DEPTHS)
        raise SystemExit(f"thinking_depth must be one of: {choices}")

    if not isinstance(config.get("configured_at"), str) or not config["configured_at"].strip():
        raise SystemExit("Workflow/config.json must contain configured_at")
    return config


def build_runtime_config(args: argparse.Namespace, configured_at: str) -> dict:
    config = {
        "workflow": "chef-worker-reviewer-workflow",
        "version": WORKFLOW_VERSION,
        "configured_at": configured_at,
        "models": {
            "main": (args.main_model.strip() if args.main_model else "current-main-conversation"),
            "chief": args.chef_model.strip(),
            "worker": args.worker_model.strip(),
            "reviewer": args.reviewer_model.strip(),
        },
        "max_worker_concurrency": args.max_worker_concurrency,
        "thinking_depth": args.thinking_depth,
    }
    return validate_runtime_config(config)


def load_runtime_config(path: Path) -> dict:
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(config, dict):
        raise SystemExit(f"{path} must contain a JSON object")
    return validate_runtime_config(config)


def resolve_file_policy(root: Path, args: argparse.Namespace) -> str:
    agents_path = root / "AGENTS.md"
    memory_path = root / "MEMORY.md"
    unmanaged = []
    if agents_path.exists() and AGENTS_START not in agents_path.read_text(encoding="utf-8"):
        unmanaged.append(str(agents_path))
    if memory_path.exists() and MEMORY_START not in memory_path.read_text(encoding="utf-8"):
        unmanaged.append(str(memory_path))

    if args.confirm_overwrite and args.file_policy != "overwrite":
        raise SystemExit("--confirm-overwrite is valid only with --file-policy overwrite")
    if args.file_policy == "overwrite" and not args.confirm_overwrite:
        raise SystemExit("Overwriting project files requires --confirm-overwrite")
    if unmanaged and args.file_policy is None:
        found = ", ".join(unmanaged)
        raise SystemExit(
            f"Existing unmanaged project file(s) detected: {found}. "
            "Ask the user to choose merge or overwrite before rerunning."
        )
    return args.file_policy or "merge"


def migrate_managed_paths(root: Path) -> None:
    for path, start, end in (
        (root / "AGENTS.md", AGENTS_START, AGENTS_END),
        (root / "MEMORY.md", MEMORY_START, "<!-- chef-worker-reviewer-workflow:memory:end -->"),
    ):
        if not path.is_file():
            continue
        existing = path.read_text(encoding="utf-8")
        start_index = existing.find(start)
        if start_index < 0:
            continue
        end_index = existing.find(end, start_index)
        if end_index < 0:
            raise SystemExit(f"Found {start!r} without its closing marker {end!r} in {path}")
        end_index += len(end)
        managed = existing[start_index:end_index].replace(".workflow", VISIBLE_WORKFLOW_DIRNAME)
        updated = existing[:start_index] + managed + existing[end_index:]
        if updated != existing:
            path.write_text(updated, encoding="utf-8")
            print(f"updated legacy workflow paths in managed section of {path}")

    manifest_path = root / VISIBLE_WORKFLOW_DIRNAME / "manifest.json"
    if not manifest_path.is_file():
        return
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print(f"preserved non-JSON legacy manifest {manifest_path}")
        return
    if not isinstance(manifest, dict):
        print(f"preserved non-object legacy manifest {manifest_path}")
        return
    manifest["version"] = WORKFLOW_VERSION
    manifest["artifact_root"] = VISIBLE_WORKFLOW_DIRNAME
    manifest["runtime_config"] = f"{VISIBLE_WORKFLOW_DIRNAME}/config.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"updated migrated manifest {manifest_path}")


def resolve_workflow_root(root: Path, args: argparse.Namespace) -> Path:
    visible_root = root / VISIBLE_WORKFLOW_DIRNAME
    legacy_root = root / LEGACY_WORKFLOW_DIRNAME
    if not legacy_root.exists():
        return visible_root
    if visible_root.exists():
        raise SystemExit(
            f"Both {visible_root} and legacy {legacy_root} exist. "
            "Resolve the two workflow directories explicitly before continuing."
        )
    if not args.migrate_legacy:
        raise SystemExit(
            f"Legacy hidden workflow directory detected at {legacy_root}. "
            f"Re-run with --migrate-legacy to copy it to visible {visible_root}; "
            "the legacy directory will be preserved."
        )
    if args.dry_run:
        raise SystemExit("--migrate-legacy cannot be combined with --dry-run")
    if not legacy_root.is_dir():
        raise SystemExit(f"Legacy workflow path is not a directory: {legacy_root}")
    staging_parent = Path(tempfile.mkdtemp(prefix=".Workflow-migration-", dir=str(root)))
    try:
        staged_root = staging_parent / VISIBLE_WORKFLOW_DIRNAME
        shutil.copytree(legacy_root, staged_root)
        staged_root.replace(visible_root)
    except OSError as exc:
        shutil.rmtree(staging_parent, ignore_errors=True)
        raise SystemExit(f"Legacy workflow migration failed before creating {visible_root}: {exc}") from exc
    shutil.rmtree(staging_parent, ignore_errors=True)
    migrate_managed_paths(root)
    print(f"migrated legacy {legacy_root} to visible {visible_root}; legacy directory preserved")
    return visible_root


def resolve_runtime_config(workflow_root: Path, args: argparse.Namespace) -> tuple[dict, bool]:
    config_path = workflow_root / "config.json"
    supplied = [getattr(args, name) is not None for name in CONFIG_ARG_NAMES]
    supplied_count = sum(supplied)
    if supplied_count not in (0, len(CONFIG_ARG_NAMES)):
        raise SystemExit("Provide all five runtime configuration values together")
    if args.main_model is not None and supplied_count != len(CONFIG_ARG_NAMES):
        raise SystemExit("--main-model must be supplied together with the five runtime configuration values")
    if args.reconfigure and supplied_count != len(CONFIG_ARG_NAMES):
        raise SystemExit("--reconfigure requires all five runtime configuration values")

    if config_path.exists():
        existing = load_runtime_config(config_path)
        if args.reconfigure:
            return build_runtime_config(args, timestamp()), True
        if supplied_count:
            raise SystemExit("Configuration already exists; use --reconfigure to change it")
        print(f"loaded existing runtime configuration from {config_path}")
        return existing, False

    if supplied_count != len(CONFIG_ARG_NAMES):
        raise SystemExit(
            "First use requires Chief model, Worker model, Reviewer model, "
            "maximum Worker concurrency, and thinking depth"
        )
    return build_runtime_config(args, timestamp()), True


def replace_marked_block(existing: str, block: str, start: str, end: str) -> str:
    start_index = existing.find(start)
    if start_index < 0:
        return existing.rstrip() + "\n\n" + block.strip() + "\n"

    end_index = existing.find(end, start_index)
    if end_index < 0:
        raise ValueError(f"Found {start!r} without its closing marker {end!r}")
    end_index += len(end)
    suffix = "\n" if not existing[end_index:].endswith("\n") else ""
    return existing[:start_index].rstrip() + "\n" + block.strip() + existing[end_index:] + suffix


def write_text(path: Path, content: str, dry_run: bool) -> None:
    if dry_run:
        print(f"DRY-RUN would write {path}")
        return
    path.write_text(content, encoding="utf-8")
    print(f"created/updated {path}")


def ensure_memory(path: Path, block: str, runtime_block: str, dry_run: bool) -> str:
    if not path.exists():
        write_text(path, "# Project Memory\n\n" + block, dry_run)
        return "created"

    existing = path.read_text(encoding="utf-8")
    if MEMORY_START in existing:
        if MEMORY_RUNTIME_START in existing and MEMORY_RUNTIME_END in existing:
            updated = replace_marked_block(existing, runtime_block, MEMORY_RUNTIME_START, MEMORY_RUNTIME_END)
            if updated != existing:
                write_text(path, updated, dry_run)
            else:
                print(f"preserved existing {path}; workflow memory already initialized")
        else:
            heading = "## Workflow memory"
            heading_end = existing.find("\n", existing.find(heading)) + 1 if heading in existing else existing.find("\n", existing.find(MEMORY_START)) + 1
            if heading_end <= 0:
                raise ValueError(f"Could not find an insertion point in {path}")
            updated = existing[:heading_end] + "\n" + runtime_block + existing[heading_end:]
            write_text(path, updated, dry_run)
            print(f"added runtime configuration section to existing {path}")
        return "preserved"

    write_text(path, existing.rstrip() + "\n\n" + block, dry_run)
    print(f"appended managed workflow memory to {path}; existing content preserved")
    return "appended"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--project-name")
    parser.add_argument("--main-model")
    parser.add_argument("--chief", default="TBD")
    parser.add_argument("--worker", default="TBD")
    parser.add_argument("--reviewer", default="TBD")
    parser.add_argument("--chief-model", "--chef-model", dest="chef_model")
    parser.add_argument("--worker-model")
    parser.add_argument("--reviewer-model")
    parser.add_argument("--max-worker-concurrency", type=int)
    parser.add_argument("--thinking-depth", choices=THINKING_DEPTHS)
    parser.add_argument("--reconfigure", action="store_true")
    parser.add_argument("--file-policy", choices=FILE_POLICIES)
    parser.add_argument("--confirm-overwrite", action="store_true")
    parser.add_argument("--migrate-legacy", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.project_root.expanduser().resolve()
    if not root.is_dir():
        raise SystemExit(f"Project root does not exist or is not a directory: {root}")

    file_policy = resolve_file_policy(root, args)
    workflow_root = resolve_workflow_root(root, args)
    runtime_config, config_changed = resolve_runtime_config(workflow_root, args)
    initialized_at = runtime_config["configured_at"]
    models = runtime_config["models"]
    values = {
        "PROJECT_NAME": args.project_name or root.name,
        "INITIALIZED_AT": initialized_at,
        "MAIN_MODEL": models.get("main") or "current-main-conversation",
        "CHIEF": args.chief,
        "WORKER": args.worker,
        "REVIEWER": args.reviewer,
        "CHIEF_MODEL": models["chief"],
        "WORKER_MODEL": models["worker"],
        "REVIEWER_MODEL": models["reviewer"],
        "MAX_WORKER_CONCURRENCY": str(runtime_config["max_worker_concurrency"]),
        "THINKING_DEPTH": runtime_config["thinking_depth"],
    }
    agents_template = AGENTS_TEMPLATE.read_text(encoding="utf-8")
    memory_template = MEMORY_TEMPLATE.read_text(encoding="utf-8")
    agents_block = render(agents_template, values)
    memory_block = render(memory_template, values)
    runtime_start = memory_template.index(MEMORY_RUNTIME_START)
    runtime_end = memory_template.index(MEMORY_RUNTIME_END, runtime_start) + len(MEMORY_RUNTIME_END)
    runtime_block = render(memory_template[runtime_start:runtime_end], values)

    directories = [
        workflow_root / "tasks",
        workflow_root / "results",
        workflow_root / "reviews",
        workflow_root / "review-bundles",
        workflow_root / "decisions",
    ]
    if not args.dry_run:
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
    else:
        for directory in directories:
            print(f"DRY-RUN would ensure directory {directory}")

    initial_files = {
        workflow_root / "PLAN.md": """# Workflow Plan\n\n## Objective\n\nPending Initial Chief Planning.\n\n## User Requirements\n\nPending Initial Chief Planning.\n\n## Non-Goals\n\nPending Initial Chief Planning.\n\n## Repository Understanding\n\nPending Initial Chief Planning.\n\n## Proposed Approach\n\nPending Initial Chief Planning.\n\n## Key Design Decisions\n\nPending Initial Chief Planning.\n\n## Critical Invariants\n\nPending Initial Chief Planning.\n\n## Global Acceptance Criteria\n\nPending Initial Chief Planning.\n\n## Task Graph\n\nPending Initial Chief Planning. Record semantic dependencies only; do not record runtime concurrency here.\n\n## Risks / Uncertainties\n\nPending Initial Chief Planning.\n\n## Main Flexibility\n\nPending Initial Chief Planning.\n\n## Chief-Owned Decisions\n\nPending Initial Chief Planning.\n""",
        workflow_root / "MAIN_BRIEF.md": """# Main Orchestrator Brief\n\n## Current Mission\n\nPending Initial Chief Planning.\n\n## Execution Starting Point\n\nPending Initial Chief Planning. List tasks whose dependencies are satisfied; do not prescribe concurrency here.\n\n## Runtime Authority\n\nMain owns runtime dispatch, concurrency, retries, evidence collection, state maintenance, and bounded adaptations inside the accepted plan.\n\n## Do Not Decide Without Chief\n\nPending Initial Chief Planning.\n\n## Reviewer Failure Policy\n\nA formal Reviewer `FAIL` increments the task's Worker failure count and is reported to Chief for a decision.\n\n## Worker Failure Policy\n\nAfter two formal Reviewer `FAIL` verdicts for the same task, use an isolated Expert Worker when Chief has not chosen to replan.\n\n## Important Invariants\n\nPending Initial Chief Planning.\n\n## Escalation Guidance\n\nPending Initial Chief Planning.\n\n## Relevant Artifact Map\n\nSee `PLAN.md`, `MEMORY.md`, `STATE.json`, `tasks/`, `results/`, `reviews/`, `review-bundles/`, `decisions/`, and `events.jsonl` under `Workflow/`.\n""",
    }
    for path, content in initial_files.items():
        if path.exists():
            print(f"preserved existing {path}")
        elif args.dry_run:
            print(f"DRY-RUN would write {path}")
        else:
            path.write_text(content, encoding="utf-8")
            print(f"created {path}")

    state_path = workflow_root / "STATE.json"
    if state_path.exists():
        print(f"preserved existing {state_path}")
    else:
        state = {
            "workflow": "chef-worker-reviewer-workflow",
            "version": WORKFLOW_VERSION,
            "workflow_status": "READY",
            "tasks": {},
            "active_agent_jobs": [],
            "blockers": [],
            "latest_runtime_update": initialized_at,
        }
        if args.dry_run:
            print(f"DRY-RUN would write {state_path}")
        else:
            state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
            print(f"created {state_path}")

    events_path = workflow_root / "events.jsonl"
    if events_path.exists():
        print(f"preserved existing {events_path}")
    elif args.dry_run:
        print(f"DRY-RUN would create {events_path}")
    else:
        events_path.write_text("", encoding="utf-8")
        print(f"created {events_path}")

    config_path = workflow_root / "config.json"
    if config_changed:
        if args.dry_run:
            print(f"DRY-RUN would write {config_path}")
        else:
            config_path.write_text(json.dumps(runtime_config, indent=2) + "\n", encoding="utf-8")
            print(f"created/updated {config_path}")

    agents_path = root / "AGENTS.md"
    if file_policy == "overwrite":
        updated_agents = "# Agent Instructions\n\n" + agents_block
    elif agents_path.exists():
        existing_agents = agents_path.read_text(encoding="utf-8")
        updated_agents = replace_marked_block(existing_agents, agents_block, AGENTS_START, AGENTS_END)
    else:
        updated_agents = "# Agent Instructions\n\n" + agents_block
    write_text(agents_path, updated_agents, args.dry_run)

    memory_path = root / "MEMORY.md"
    if file_policy == "overwrite":
        write_text(memory_path, "# Project Memory\n\n" + memory_block, args.dry_run)
    else:
        ensure_memory(memory_path, memory_block, runtime_block, args.dry_run)

    manifest_path = workflow_root / "manifest.json"
    if manifest_path.exists():
        print(f"preserved existing {manifest_path}")
    else:
        manifest = {
            "workflow": "chef-worker-reviewer-workflow",
            "version": WORKFLOW_VERSION,
            "project": values["PROJECT_NAME"],
            "initialized_at": initialized_at,
            "role_assignments": {
                "main": "current-main-conversation",
                "chief": args.chief,
                "worker": args.worker,
                "reviewer": args.reviewer,
            },
            "artifact_root": VISIBLE_WORKFLOW_DIRNAME,
            "runtime_config": f"{VISIBLE_WORKFLOW_DIRNAME}/config.json",
            "plan": f"{VISIBLE_WORKFLOW_DIRNAME}/PLAN.md",
            "main_brief": f"{VISIBLE_WORKFLOW_DIRNAME}/MAIN_BRIEF.md",
            "state": f"{VISIBLE_WORKFLOW_DIRNAME}/STATE.json",
            "events": f"{VISIBLE_WORKFLOW_DIRNAME}/events.jsonl",
            "review_bundles": f"{VISIBLE_WORKFLOW_DIRNAME}/review-bundles/",
        }
        if args.dry_run:
            print(f"DRY-RUN would write {manifest_path}")
        else:
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            print(f"created {manifest_path}")

    print(f"workflow initialized at {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
