# Project file contract

The workflow uses two root-level Markdown files for different kinds of truth.

| File | Purpose | Primary owner | Update style |
|---|---|---|---|
| `AGENTS.md` | Rules that future agents must follow | Chief plus project maintainers | Stable, reviewed policy |
| `.workflow/config.json` | Runtime model and scheduling configuration | Chief plus user | Replace only through explicit reconfiguration |
| `MEMORY.md` | What this workflow has learned or done | Chief maintains state; Worker and Reviewer append evidence | Append-oriented ledger |

Do not use `MEMORY.md` to hide a new rule. Put a rule in `AGENTS.md` and record the decision that introduced it in `MEMORY.md`. Do not put the active model selection only in prose; `.workflow/config.json` is the source of truth.

## Pre-generation conflict check

Before the first generation, inspect both root-level files:

| Detection | Action |
|---|---|
| File absent | Create it after runtime configuration is confirmed |
| File has the workflow marker | Treat as initialized; preserve history and update the managed section only |
| File exists without the workflow marker | Ask the user to merge, overwrite, or cancel before writing |

`merge` preserves all existing content and adds or updates only the managed block. `overwrite` replaces the entire detected file and therefore requires an explicit second confirmation. `cancel` performs no file generation. Never choose a policy from an ambiguous acknowledgement.

## First-run runtime configuration

Before the first task, ask for and persist:

| Setting | Required value |
|---|---|
| Chief/Chef model | Exact model identifier for the current main conversation, exposed by the harness |
| Worker model | Exact model identifier exposed by the harness |
| Reviewer model | Exact model identifier exposed by the harness |
| Worker maximum concurrency | Positive integer |
| Default thinking depth | Supported reasoning level, for example `low`, `medium`, `high`, or `xhigh` |

Use a single default thinking depth for the initial version. Add per-role overrides only when the user explicitly asks for them; otherwise the workflow becomes harder to reason about and reproduce.

The configuration file should contain:

```json
{
  "workflow": "chef-worker-reviewer-workflow",
  "version": "1.1",
  "configured_at": "<timestamp>",
  "models": {
    "chief": "<model-id>",
    "worker": "<model-id>",
    "reviewer": "<model-id>"
  },
  "max_worker_concurrency": 1,
  "thinking_depth": "medium"
}
```

On later runs, load this file without asking again. Reconfiguration requires explicit user intent and a corresponding MEMORY decision entry.

## AGENTS.md required content

Keep the managed section short and operational. It should contain:

1. Workflow identity and version.
2. Chief, Worker, and Reviewer responsibilities.
3. Explicit permissions and prohibitions for each role.
4. Task lifecycle and allowed transitions.
5. Definition of evidence and review verdicts.
6. Repair and escalation thresholds.
7. Durable artifact paths, including `.workflow/tasks/`, `.workflow/results/`, `.workflow/reviews/`, and `.workflow/decisions/`.
8. Runtime configuration rules, including the concurrency ceiling and no-silent-fallback rule.
9. Privacy and safety rules, especially the prohibition on secrets in Markdown records.

Do not put volatile task status, current model names, or long work logs in `AGENTS.md`. Those belong in `MEMORY.md` or the packet files.

When `AGENTS.md` already exists, preserve everything outside the skill's markers:

```text
<!-- chef-worker-reviewer-workflow:start -->
...
<!-- chef-worker-reviewer-workflow:end -->
```

If existing project instructions conflict with the managed section, stop the workflow and record the conflict for Chief or the user. Do not silently overwrite the project rule.

The initializer accepts `--file-policy merge` for the non-destructive path. It accepts `--file-policy overwrite` only with `--confirm-overwrite`.

## MEMORY.md required content

Keep the memory file concise and link detailed evidence instead of copying it. Include:

### Workflow identity

- project name and root;
- workflow version and initialization time;
- artifact root;
- source contract (`AGENTS.md`).

### Runtime configuration

Record the declared current main-conversation Chef model, the Worker and Reviewer models, the Worker concurrency ceiling, thinking depth, and a pointer to `.workflow/config.json`. Keep this section synchronized with the config file after an approved reconfiguration. The declared Chef model is not by itself proof of final upstream routing.

### Role assignments

Record logical owners or agent IDs, not credentials:

| Role | Owner / agent ID | Scope | Status |
|---|---|---|---|
| Chief | ... | planning, decisions, routing | active |
| Worker | ... | assigned implementation task | active/idle |
| Reviewer | ... | independent review | active/idle |

### Current state

Record the active task, workflow status, next action, blocker, and last verified timestamp.

### Task ledger

Use one row per task:

| Task ID | Objective | Owner | Status | Review | Evidence |
|---|---|---|---|---|---|
| T-001 | ... | Worker | EXECUTING | pending | `.workflow/tasks/T-001.md` |

### Decisions

For each non-trivial decision, record date, decision, rationale, authority, and affected task or artifact.

### Work log

Record short events with timestamp, task, role, action, result, evidence pointer, and next action. Keep detailed output in `.workflow/`.

### Review findings

Record finding ID, severity, evidence, disposition, repair task, and verification result. Do not erase a finding after repair; mark it resolved.

### Risks and follow-ups

Record unresolved compatibility, security, data, performance, or release risks with an owner and next check.

## Ownership matrix

| Artifact | Chief | Worker | Reviewer |
|---|---:|---:|---:|
| `AGENTS.md` policy | approve/write | propose | flag conflict |
| `.workflow/config.json` | approve/write | read | read |
| `MEMORY.md` state | maintain | append evidence | append review evidence |
| Task packet | write/approve | read | read |
| Implementation | approve scope | write | read |
| Work result | read | write | read |
| Review report | read/decide | read/repair | write |
| Decision packet | write | provide evidence | provide evidence |

## Privacy and retention

Never record secrets, access tokens, private keys, passwords, or sensitive personal data. Redact command output before linking or summarizing it. Prefer a stable path and a short result over a pasted log.
