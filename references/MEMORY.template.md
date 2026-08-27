<!-- chef-worker-reviewer-workflow:memory:start -->
## Durable project memory

- Workflow version: `1.4` (v1.4.1 repair)
- Project: `{{PROJECT_NAME}}`
- Initialized at: `{{INITIALIZED_AT}}`
- Artifact root: `Workflow/`
- Source contract: `AGENTS.md`
- Runtime state: `Workflow/STATE.json`
- Runtime events: `Workflow/events.jsonl`
- Watchdog settings: `Workflow/watchdog.json`
- Role heartbeats: `Workflow/heartbeats.json`
- Watchdog alerts: `Workflow/watchdog-alerts.jsonl`

### Runtime configuration summary

<!-- chef-worker-reviewer-workflow:runtime-config:start -->

- Main/Orchestrator model declaration: `{{MAIN_MODEL}}` (current main conversation; routing may be unverified)
- Chief model: `{{CHIEF_MODEL}}`
- Worker model: `{{WORKER_MODEL}}`
- Reviewer model: `{{REVIEWER_MODEL}}`
- Worker maximum concurrency: `{{MAX_WORKER_CONCURRENCY}}`
- Main thinking depth: `{{MAIN_THINKING_DEPTH}}`
- Chief thinking depth: `{{CHIEF_THINKING_DEPTH}}`
- Worker thinking depth: `{{WORKER_THINKING_DEPTH}}`
- Reviewer thinking depth: `{{REVIEWER_THINKING_DEPTH}}`
- Configuration file: `Workflow/config.json`
- Watchdog interval: 600 seconds by default; suspected stalls are reported to Main for a decision

<!-- chef-worker-reviewer-workflow:runtime-config:end -->

### Project facts

Record stable repository facts that future agents need. Do not copy routine command output.

### Confirmed decisions

Record high-value decisions as concise summaries with links to `Workflow/decisions/`.

### Important discoveries

Record findings that remain useful after the current task ends.

### Known pitfalls

Record recurring traps, compatibility hazards, or verification caveats.

### User constraints

Record user requirements that continue to affect future work.

### Durable risks

Record unresolved risks with an owner and next check.

### Memory candidates

Worker and Reviewer may propose additions here in their Result/Review artifacts. Main is the Memory Gatekeeper and decides whether a candidate has durable value before merging it into this file.

### Retention boundary

Do not record Worker/Reviewer started or finished events, routine PASS/FAIL trace, shell exits, retries, interruptions, continuations, timeouts, waiting, status sync, concurrency checks, or ordinary tool logs here. Those belong in `Workflow/events.jsonl`, `Workflow/STATE.json`, task artifacts, results, reviews, or decisions.

### Update rules

- Keep this file concise, high-density, and append-oriented.
- Do not delete old history during v1.3 → v1.4 compatibility migration.
- Record a Memory Delta when a Chief decision adds, supersedes, or removes durable knowledge.
- Never store secrets or sensitive personal data.
<!-- chef-worker-reviewer-workflow:memory:end -->
