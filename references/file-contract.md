# v1.4.1 repair: v1.4 Workflow file contract

The workflow is an LLM Conductor with deterministic guardrails. Main owns runtime execution; Chief owns semantic planning and plan-level decisions.

## Source of truth by concern

| Artifact | Purpose | Primary owner | Update style |
|---|---|---|---|
| `AGENTS.md` | Stable rules and role boundaries | Chief plus maintainers | Managed block only |
| `MEMORY.md` | Durable project knowledge and confirmed decisions | Main gates; Chief proposes | Concise, append-oriented |
| `Workflow/config.json` | Declared role models, Worker ceiling, and per-role thinking depths | User/Chief | Explicit reconfiguration |
| `Workflow/PLAN.md` | Semantic plan, requirements, decisions, invariants, dependencies | Chief | Plan-level updates only |
| `Workflow/MAIN_BRIEF.md` | Short Chief → Main Runtime Handoff | Chief | Replace/update on plan delta |
| `Workflow/STATE.json` | Current operational projection | Main/script | Small structured updates |
| `Workflow/events.jsonl` | Append-only runtime facts | Main/script | One JSON object per line |
| `Workflow/watchdog.json` | Visible Watchdog settings, PID, last check, and open-alert projection | Main/Watchdog | Updated every check |
| `Workflow/heartbeats.json` | Latest heartbeat for Main and delegated roles | Main/roles/script | Updated before/after long calls and runtime events |
| `Workflow/watchdog-alerts.jsonl` | Append-only suspected-stall reports for Main | Watchdog | One JSON object per alert |

`PLAN.md` records semantic dependencies, never runtime concurrency. `STATE.json` answers “where are we now?”; `MEMORY.md` answers “what remains valuable later?”; events answer “what happened during execution?”.

## Initialization and compatibility

Before writing root files, detect `AGENTS.md` and `MEMORY.md`: absent means create; a managed marker means preserve history and update only the managed block; an unmarked file requires explicit `merge`, explicit overwrite confirmation, or `cancel`. Never infer overwrite permission.

`Workflow/` is the canonical visible directory. A legacy `.workflow/` is never silently duplicated. With explicit `--migrate-legacy`, copy it to `Workflow/`, preserve the old directory as backup, update managed path references, and create missing v1.4 artifacts. Existing v1.3 config, tasks, results, reviews, and history remain readable.

The Watchdog checks every 600 seconds by default. It reports stale role heartbeats or active-task runtime updates as a suspected network/provider/unresponsive-agent stall; it does not assert the cause, restart agents, change models, or schedule repairs. Main owns the response. No hidden workflow directory is created.

The v1.4 config may contain `models.main` and stores `thinking_depth` as four role keys: `main`, `chief`, `worker`, and `reviewer`. Older configs without `models.main` are valid and mean `current-main-conversation`; a legacy single depth is expanded to all four roles. Do not pretend that a local declaration proves upstream routing. A v1.3 invocation with the original five runtime flags remains accepted.

## PLAN.md

`Workflow/PLAN.md` must contain:

- Objective and explicit User Requirements;
- Non-Goals;
- concise Repository Understanding;
- Proposed Approach;
- Key Design Decisions;
- Critical Invariants;
- Global Acceptance Criteria;
- Task Graph with semantic dependencies only;
- Risks / Uncertainties;
- Main Flexibility (adaptation allowed inside the plan);
- Chief-Owned Decisions (changes that require Chief).

Initial Global Planning is performed by Chief for a large initial prompt. Chief creates all currently reasonable initial task packets and high-value Memory candidates, then writes `MAIN_BRIEF.md`. Chief does not plan parallel waves or resource placement.

## MAIN_BRIEF.md

Keep this shorter than `PLAN.md`. Include Current Mission, Execution Starting Point (dependency-ready tasks only), Main Runtime Authority, Do Not Decide Without Chief, Reviewer/Worker failure policy, Important Invariants, Escalation Guidance, and the artifact map. Do not prescribe concurrency here.

## STATE.json

The initializer creates a small state object:

```json
{
  "workflow": "chef-worker-reviewer-workflow",
  "version": "1.4",
  "workflow_status": "READY",
  "tasks": {
    "T-001": {
      "status": "REVIEWING",
      "worker_attempts": 1,
      "review_attempts": 1,
      "worker_failures": 0,
      "latest_runtime_update": "<timestamp>"
    }
  },
  "active_agent_jobs": [],
  "blockers": [],
  "latest_runtime_update": "<timestamp>"
}
```

Only formal Reviewer `FAIL` increments `worker_failures`. FAIL #1 sets Chief escalation required. FAIL #2 routes to a fresh Expert Worker by default, unless explicit plan-level evidence requires Chief; Expert Worker FAIL routes to Chief through Main. Worker self-repair, tool errors, path errors, temporary timeouts, and intermediate test failures do not. Main may update state for runtime conditions; it must not change semantic task dependencies without Chief.

`active_agent_jobs` is optional/reserved metadata and is not the authoritative source for liveness or completion. Task status, `latest_runtime_update`, `heartbeats.json`, and Watchdog alerts are the operational evidence.

## Runtime events

`Workflow/events.jsonl` stores structured events such as `workflow_initialized`, `task_started`, `worker_dispatched`, `worker_completed`, `review_started`, `review_passed`, `review_failed`, `expert_worker_dispatched`, `subagent_interrupted`, `subagent_resume_requested`, `subagent_resumed`, `repair_created`, `decision_recorded`, `state_changed`, `blocked`, and `task_closed`. Each event should include `event_id`, `event_type`, timestamp, task ID, role, concise action/result, evidence, and next action; continuation events should include the session handle when available and the safe checkpoint. Use a file lock or equivalent serialized append/update so concurrent events are not lost. Runtime events must not be appended to `MEMORY.md`.

Transient network/provider errors, timeouts, rate limits, and context or thinking-token limits are recoverable interruptions. Main preserves the original Subagent/session and sends `继续` to that same session before considering any replacement. A replacement requires evidence that the session is unavailable/expired or that bounded continuation attempts failed; it does not inherit the original identity by assertion.

`workflow_status` is recalculated from all task states after every task update. It is not a projection of the last event: any `BLOCKED` task blocks the workflow, `REPAIRING` takes precedence over active work, active `EXECUTING`/`REVIEWING` tasks prevent `PASSED`, and the workflow is `PASSED` only when every task is `PASSED`.

## Task packet

Each `Workflow/tasks/<task-id>.md` contains Objective, Context, Dependencies, Scope, Out of Scope, Relevant Files / Areas, Expected / Allowed Write Scope, Implementation Guidance, Constraints, Acceptance Criteria, Required Verification, Reviewer Focus, Deliverables, and the Main concurrency decision: planned Worker/Reviewer counts, isolation boundaries, dependency assumptions, test isolation, and quality rationale. The last fields are runtime choices, not Chief’s semantic DAG.

Relevant files are guidance, not an information boundary. Workers and Reviewers may inspect additional repository evidence.

## Worker Result

Each `Workflow/results/<task-id>.md` records Task ID, Status, Summary, Changed/Added/Deleted Files, per-criterion results, Tests Run (command, exit code, executed/passed/failed counts), Evidence, Deviations, Unexpected Repository State, Unresolved Issues, Reviewer Focus, and Memory Candidates. Repair attempts must remain traceable; do not silently erase an earlier result.

`exit_code == 0` with `executed_tests == 0` is `INVALID_TEST_EXECUTION`, never a valid `PASS`.

## Reviewer report

Each `Workflow/reviews/<task-id>-r<N>.md` includes Verdict (`PASS`, `FAIL`, or `BLOCKED`), Findings, Evidence, Likely Root Cause, Recommended Solution, Affected Scope, Regression Risks, and Confidence. Findings use `BLOCKER`, `MAJOR`, `MINOR`, or `QUESTION`. A Reviewer recommendation is not repair authorization or architecture authority. After an Expert Worker, review returns to the same Reviewer policy: prefer the same persistent Reviewer session; otherwise use the same Reviewer model, role contract, and reasoning/configuration, and supply previous findings. A session ID is not mandatory.

## Review Bundle

`Workflow/review-bundles/<task-id>/<attempt>/` is bundle-first Reviewer context, not an information boundary. Each repair or changed evidence set gets a new attempt; do not overwrite an existing bundle. Generated bundle files are read-only snapshots; `immutable` does not mean that the underlying repository cannot change. It should contain:

- `metadata.json` — task, base/review revisions, diff source and stability signal, changed files, expected scope, scope signal, and source hashes;
- `task-packet.md` and `worker-result.md`;
- `changed-files.txt` and `diff.patch`;
- `tests.json`;
- `scope-check.json`;
- `review-context.md`.

The bundle records actual evidence as a starting snapshot. If the task packet, result, or diff changes after bundling, create a new review attempt rather than treating the old bundle as current.

## Decision artifact

Important Chief decisions go in `Workflow/decisions/D-xxx.md` with Trigger, New Evidence, Decision (`REPAIR`, `REPLAN`, or `ASK_USER`), Reason, Plan Impact, Affected Tasks, Memory Delta, Task Changes, and required next state. A concise escalation packet is input to Chief, not an information boundary; Chief may inspect any needed files, history, tests, diffs, or artifacts.

## Authority and concurrency

Main owns runtime concurrency. Chief owns semantic dependency. Programs may emit `SAFE`, `WARNING`, or `BLOCKED` for dependency, expected-write-scope, shared-resource, and Reviewer-read-stability checks, but do not replace Main with an automatic scheduler. Main may choose serial execution even after `SAFE`. A global scope overlap scan is a `WARNING`, but an actual requested parallel Worker pair with shared worktree plus exact or parent/child overlapping write scopes is `BLOCKED` unless isolated worktrees are declared. Reviewer/Worker overlap is `BLOCKED` without a stable task snapshot, revision boundary, or isolated worktree.

## Durable MEMORY

`MEMORY.md` stores Project Facts, Confirmed Decisions, Important Discoveries, Known Pitfalls, User Constraints, Durable Risks, and approved Memory Candidates. Main is the Memory Gatekeeper. Worker and Reviewer propose candidates; Main merges only facts likely to remain valuable after the current task. Routine started/finished/PASS/FAIL/retry/timeout/status/tool events stay in `events.jsonl`, `STATE.json`, task artifacts, results, reviews, or decisions.

## Ownership matrix

| Artifact | Main | Chief | Worker | Reviewer |
|---|---:|---:|---:|---:|
| `PLAN.md` / `MAIN_BRIEF.md` | read/route | write/decide | read | read |
| `STATE.json` / `events.jsonl` | maintain | read | report | report |
| `MEMORY.md` | gate/merge | propose | propose | propose |
| Task packet | create runtime tasks | create initial tasks | read | read |
| Implementation | approve adaptation | no routine edits | write | read |
| Review Bundle | build/route | read | provide evidence | read/verify |
| Decision artifact | route | write | provide evidence | provide evidence |

Never store secrets, access tokens, private keys, passwords, or sensitive personal data in these artifacts.
