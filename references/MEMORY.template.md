<!-- chef-worker-reviewer-workflow:memory:start -->
## Workflow memory

- Workflow version: `1.3`
- Project: `{{PROJECT_NAME}}`
- Initialized at: `{{INITIALIZED_AT}}`
- Artifact root: `Workflow/`
- Source contract: `AGENTS.md`

### Runtime configuration

<!-- chef-worker-reviewer-workflow:runtime-config:start -->

- Chief/Chef model (current main conversation): `{{CHIEF_MODEL}}`
- Worker model: `{{WORKER_MODEL}}`
- Reviewer model: `{{REVIEWER_MODEL}}`
- Worker maximum concurrency: `{{MAX_WORKER_CONCURRENCY}}`
- Default thinking depth: `{{THINKING_DEPTH}}`
- Configuration file: `Workflow/config.json`

<!-- chef-worker-reviewer-workflow:runtime-config:end -->

### Role assignments

| Role | Owner / agent ID | Scope | Status |
|---|---|---|---|
| Chief | `{{CHIEF}}` | planning, decisions, routing | active |
| Worker | `{{WORKER}}` | bounded implementation tasks | idle |
| Reviewer | `{{REVIEWER}}` | independent verification | idle |

### Current state

- Workflow status: `READY`
- Active task: `none`
- Next action: Chief creates the first task packet.
- Blocker: `none`
- Last verified: `{{INITIALIZED_AT}}`

### Task ledger

| Task ID | Objective | Owner | Status | Review | Evidence |
|---|---|---|---|---|---|
| `T-000` | Initialize workflow contract | Chief | `PASSED` | `N/A` | `AGENTS.md`, `Workflow/config.json`, `Workflow/manifest.json` |

### Decisions

No non-trivial decisions recorded yet.

### Work log

<!-- chef-worker-reviewer-workflow:work-log:start -->
No workflow events recorded yet.
<!-- chef-worker-reviewer-workflow:work-log:end -->

### Review findings

No review findings recorded yet.

### Risks and follow-ups

- Confirm project-specific test commands before dispatching the first Worker task.
- Keep detailed task, result, and review evidence in `Workflow/` and link to it here.

### Update rules

- Chief owns current state, task status, and decisions.
- Worker appends implementation evidence and deviations.
- Reviewer appends findings and verification results.
- Keep entries concise, append-oriented, and free of secrets.
- Do not delete resolved findings; mark them resolved with evidence.
<!-- chef-worker-reviewer-workflow:memory:end -->
