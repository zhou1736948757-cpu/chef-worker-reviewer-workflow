---
name: chef-worker-reviewer-workflow
description: Orchestrate an LLM Conductor plus deterministic guardrails workflow with Main/Orchestrator, persistent Chief, Worker, Reviewer, and temporary Expert Worker roles. Use for initial global planning, bounded implementation, independent review, runtime state and evidence tracking, quality-gated concurrency, repair/escalation loops, and visible Workflow artifacts.
---

# Main / Chief / Worker / Reviewer Workflow

Use this skill as an LLM Conductor with deterministic guardrails. “Chef” is a user-facing alias for Chief, not a synonym for Main.

## Operating model

Keep these responsibilities separate:

- Main/Orchestrator is the current main conversation and the Runtime center. It owns dispatch, runtime order, effective concurrency, retries, evidence collection, state maintenance, and bounded adaptation inside an accepted plan.
- Chief is a persistent high-intelligence subagent. It owns Initial Global Planning and plan-level decisions; it is called infrequently and is not the routine Runtime orchestrator.
- Worker owns implementation and verification inside one bounded task.
- Reviewer owns independent quality judgment and evidence collection; Reviewer does not edit implementation files.
- Expert Worker is a temporary, fresh, isolated Chief-class coding subagent used for a concrete implementation problem after repeated formal Reviewer failure. It is not Chief and does not share Chief’s persistent context.

Do not treat a role name as a model name. Select models independently from the role contract.

## Pre-generation file check (mandatory)

Before generating either project file, check whether `<project-root>/AGENTS.md` and `<project-root>/MEMORY.md` already exist.

- If a file is absent, create it after the configuration questions are answered.
- If a file contains the corresponding `chef-worker-reviewer-workflow` managed marker, treat it as already initialized; preserve its history and update only the managed section when needed.
- If an existing file has no corresponding managed marker, stop before writing and tell the user exactly which files were found.

Ask the user to choose one policy for all detected unmanaged files:

1. `融合` (recommended): preserve existing content and append or update only the Skill-managed section.
2. `覆盖`: replace the entire detected file with the generated template. Explain that existing instructions or memory will be lost and require a second explicit confirmation such as `确认覆盖`.
3. `取消`: do not create or modify either file; stop the workflow.

Do not infer the user's choice from “继续”“可以” or a general approval. Treat anything other than an explicit policy choice and, for overwrite, the explicit confirmation as cancellation. Pass the selected policy to `init_project_workflow.py` with `--file-policy merge` or `--file-policy overwrite --confirm-overwrite`.

## Visible workflow directory

Use a visible, project-root `Workflow/` directory as the canonical artifact root. Do not create a hidden `.workflow/` directory for new projects. Keep `Workflow/` in the normal project tree so users can inspect packets, results, reviews, decisions, the manifest, and runtime configuration directly.

If a legacy project contains `.workflow/` but no `Workflow/`, stop and explain the migration. After explicit approval, run the initializer with `--migrate-legacy`; it copies the legacy directory to `Workflow/` and preserves `.workflow/` as a backup. If both directories exist, do not guess which is authoritative; resolve them explicitly before continuing.

## First-run setup (mandatory)

Before creating `AGENTS.md`, `MEMORY.md`, or dispatching any task, inspect `Workflow/config.json`.

If it does not exist, ask the user these six questions and wait for answers:

1. Which exact model is the Main/Orchestrator model, if the harness exposes or can route it? If Main is fixed as the current conversation, record that fact rather than inventing a routing setting.
2. Which exact model should run as the persistent Chief?
3. Which exact model should run as Worker?
4. Which exact model should run as Reviewer?
5. What is the maximum number of Workers allowed to run concurrently?
6. What default thinking depth should delegated roles use? Accept only a depth supported by the selected harness, such as `low`, `medium`, `high`, or `xhigh`.

Before asking, explain capability profiles rather than naming providers: recommended intelligence is `Chief > Reviewer > Main ≈ Worker`; expected call volume is `Worker > Main > Reviewer > Chief`; these are heuristics, not hard constraints. Main should be stable, tool-capable, fast, and cost-efficient; Chief should be strongest at planning, architecture, long context, ambiguity resolution, and re-planning; Worker should be coding/tool/repository strong and high-throughput; Reviewer should be independent, diagnostic, and root-cause oriented. Main may share Worker’s model. Do not silently invent a model, concurrency limit, or thinking depth. If the harness exposes a model or reasoning catalog, validate answers against it; otherwise preserve exact identifiers and report that runtime support still needs verification.

Persist the answers in `Workflow/config.json` using this shape:

```json
{
  "workflow": "chef-worker-reviewer-workflow",
  "version": "1.4",
  "configured_at": "<timestamp>",
  "models": {
    "main": "<model-id-or-current-main-conversation>",
    "chief": "<model-id>",
    "worker": "<model-id>",
    "reviewer": "<model-id>"
  },
  "max_worker_concurrency": 1,
  "thinking_depth": "medium"
}
```

On later invocations, read and display this configuration briefly instead of asking again. v1.3 configurations without `models.main` remain valid and are interpreted as `current-main-conversation`. Ask the configuration questions again only when the user explicitly requests reconfiguration. Record configuration changes as a durable decision, not a routine event. Do not change models, concurrency, or thinking depth halfway through an active task without a Chief decision.

## Main / Chief authority boundary

Main is the current main conversation and Runtime center. Chief is a persistent high-intelligence subagent, not the main conversation. Keep Chief’s context focused on project meaning, architecture, invariants, semantic dependencies, and plan-level decisions; do not send routine shell logs, progress noise, or every status update to Chief.

Use this rule for every proposed change:

> 既定方案内部能修 → Main。必须重新解释或改变方案 → Chief。
>
> Main owns adaptation inside an accepted plan. Chief owns interpretation and changes to the plan itself.

Main may decide Worker/Reviewer/Expert Worker dispatch, runtime order and concurrency, retries, timeout handling, tool troubleshooting, evidence collection, safe test-command corrections, bounded runtime tasks, small implementation adaptations that preserve design semantics, and operational state updates. Main must not change the user goal, architecture, confirmed interface contract, ownership model, user-visible semantics, global acceptance criteria, task objective meaning, semantic dependency graph, or confirmed constraints without Chief.

At task start, remind the user:

> 提醒：本工作流中的 Main 是当前主对话和 Runtime 编排中心；Chief 是独立的持久高智力规划与决策 Subagent。Main 负责执行调度，Worker 负责实现，Reviewer 负责独立审核，必要时由 Expert Worker 处理困难实现。

Report the declared Main and Chief models from `Workflow/config.json`. If actual routing is observable, report whether it matches; otherwise state that these are declared identities and upstream routing is unverified. Never present local configuration as proof of final routing.

## Initial Global Planning

For a large initial project prompt, Main performs only basic context preparation, then activates or spawns the persistent Chief. Chief may use broad repository exploration, deep reasoning, and multiple tool calls to produce:

- `Workflow/PLAN.md` with requirements, non-goals, repository understanding, approach, design decisions, invariants, global acceptance criteria, semantic Task DAG, risks, Main flexibility, and Chief-owned decisions;
- `Workflow/MAIN_BRIEF.md` as a concise Runtime Handoff to Main;
- all currently reasonable and foreseeable initial task packets;
- high-value durable Memory candidates for `MEMORY.md`.

Chief owns semantic dependencies, not runtime concurrency. Do not put `parallel_notes` or a concurrency plan in `PLAN.md`. After Main verifies the planning artifacts, Main takes over Runtime. If the harness cannot provide a persistent Chief, simulate the separation in distinct phases and record that limitation; do not claim persistence that does not exist.

## Runtime failure and Expert Worker

Worker Failure has one definition: only a formal Reviewer verdict of `FAIL` increments `worker_failures`. A Worker’s self-repaired test failure, shell/tool error, path error, temporary timeout, or intermediate retry does not increment it.

After every formal Reviewer `FAIL`, Main records the event and sends a concise escalation packet to Chief containing the task packet, Worker result, Reviewer result, current repository state, failure count, and the decision required. The packet is a starting point, not an information boundary; Chief may inspect any relevant files, history, tests, diffs, or artifacts. Chief returns a Decision Delta such as `REPAIR`, `REPLAN`, or `ASK_USER`; Chief does not perform routine implementation.

When the same task reaches `worker_failures >= 2`, do not mechanically repeat a normal Worker. Unless Chief chooses `REPLAN`, dispatch a temporary Expert Worker using the Chief model or a Chief-class configuration, in a fresh isolated context. Expert Worker solves only the concrete coding/debugging issue, is not Chief, cannot approve its own work, and does not share Chief’s persistent context. After Expert Worker completes, send the result back to the same Reviewer configuration (same logical Reviewer/model policy); the Reviewer checks the original finding, regressions, and acceptance criteria. If Expert Worker also receives `FAIL`, notify Chief again.

## Concurrency and quality gate

Worker and Reviewer subagents may run concurrently, but concurrency is an optimization decided by Main, not an automatic requirement. The configured `max_worker_concurrency` is a hard ceiling for Workers; Main separately chooses the effective Worker and Reviewer parallelism for each task and records the decision in the task packet. Chief defines semantic dependencies; Main owns runtime concurrency.

Main may authorize parallel execution only when all of these conditions hold:

- each subtask has a separate objective, acceptance criteria, and bounded writable scope;
- Workers do not edit the same files, shared generated outputs, schema, migration, lockfile, or other mutable state;
- there is no ordering or data dependency between subtasks, or the dependency has already been materialized as a read-only input;
- tests can run in isolated environments without shared ports, databases, fixtures, credentials, devices, or rate limits;
- each Reviewer receives the original task packet, the relevant actual diff, and enough independent evidence to reach a verdict without relying on another Reviewer’s conclusion;
- the aggregate risk, tool capacity, and observability are acceptable for the selected parallelism.

Default to serial execution when the codebase, dependencies, test isolation, or risk is unclear. Also serialize work involving security, data loss, public release, destructive operations, shared architecture decisions, or tightly coupled integration behavior unless Main has documented why parallelism remains safe. Multiple Reviewers may review one change concurrently only when their review dimensions are explicitly separated; Main must synthesize their verdicts and findings before allowing repair or completion. A Reviewer never edits implementation files to make parallel review succeed.

Before dispatch, Main records at least: planned Worker concurrency, planned Reviewer concurrency, isolation boundaries, dependency assumptions, test-isolation plan, and the reason the choice is expected not to reduce quality. `scripts/validate_task_plan.py` may emit `SAFE`, `WARNING`, or `BLOCKED` for deterministic checks, but it never schedules agents. If a parallel result conflicts, loses evidence, creates a merge ambiguity, or exposes an untested interaction, Main stops further parallel dispatch and returns the affected work to a bounded serial phase.

## Start a workflow

1. Identify the project root. Prefer the repository root when `git rev-parse --show-toplevel` succeeds; otherwise use the requested project directory or current working directory.
2. Read existing project instructions before changing anything, especially `AGENTS.md`, `MEMORY.md`, and any nearer directory-level instructions.
3. Run the pre-generation file check above. Resolve any unmanaged-file choice before creating or updating either file.
4. Complete the first-run setup above. Then initialize the project-local contract with the bundled script:

   ```bash
   python3 <skill-root>/scripts/init_project_workflow.py \
     --project-root <project-root> \
     --main-model <main-model-id-or-current-main-conversation> \
     --chief <chief-owner> \
     --worker <worker-owner> \
     --reviewer <reviewer-owner> \
     --chef-model <chief-model-id> \
     --worker-model <worker-model-id> \
     --reviewer-model <reviewer-model-id> \
     --max-worker-concurrency <positive-integer> \
     --thinking-depth <supported-depth>
   ```

   The script writes `Workflow/config.json`, creates or updates only the managed workflow section of `AGENTS.md`, creates `MEMORY.md` when absent, preserves existing user content, and creates visible `Workflow/` planning, state, event, packet, and review-bundle artifacts. On a later run, omit the configuration flags to reuse the saved configuration; pass `--reconfigure` together with the five legacy flags and optional `--main-model` only after explicit user approval. It never replaces an existing project memory file wholesale.

5. Emit the Main/Chief task-start reminder above, including configured-versus-observed model status.
6. For a large initial prompt, wait for Chief to complete `PLAN.md`, `MAIN_BRIEF.md`, and initial task packets; for a bounded follow-up inside the accepted plan, Main may create a runtime task directly.
7. Decide and record effective Worker and Reviewer concurrency using the quality gate above. Dispatch one Worker per bounded task; allow parallel Workers only when Main confirms the isolation and evidence conditions, and never exceed `max_worker_concurrency` from `Workflow/config.json`.
8. Require the Worker to write a structured result at `Workflow/results/<task-id>.md` containing changed files, per-criterion results, test counts, evidence, deviations, unresolved issues, Reviewer focus, and Memory candidates.
9. Build `Workflow/review-bundles/<task-id>/<attempt>/` when useful, then send the original task packet, bundle, actual diff, and Worker result to an independent Reviewer context. Require a structured report at `Workflow/reviews/<task-id>-r<N>.md`.
10. On `PASS`, update `STATE.json`, let Main gate Memory candidates, and close the task. On `FAIL`, increment only the formal Reviewer failure count, notify Chief with an escalation packet, and follow the Decision Delta. On `BLOCKED`, or a Chief-directed replan, write a decision artifact in `Workflow/decisions/`.

If the harness cannot create subagents, simulate the same separation in distinct phases and still persist the task, result, and review artifacts.

When dispatching, pass Worker and Reviewer their configured models and the configured `thinking_depth`; pass Chief its configured model and a planning or escalation prompt. Keep Main in the current main conversation. Treat a harness rejection as a configuration error; stop and ask whether to reconfigure instead of silently falling back to another model or depth.

## Role contracts

### Chief

Chief must:

- perform Initial Global Planning for a large prompt;
- understand the repository, requirements, non-goals, architecture, invariants, risks, and semantic dependencies;
- create the semantic Task DAG, initial task packets, `PLAN.md`, `MAIN_BRIEF.md`, and high-value Memory candidates;
- define observable acceptance criteria, verification requirements, and Reviewer focus;
- decide plan-level changes after Reviewer FAIL, architecture conflict, requirement change, or unresolved ambiguity;
- issue concise Decision Deltas (`REPAIR`, `REPLAN`, or `ASK_USER`) and record important decisions.

Chief does not plan runtime concurrency, run routine orchestration, absorb progress noise, or perform routine implementation. If Chief makes an emergency code change, route that change through the same Reviewer gate.

Chief is done with planning only when a Worker can execute without guessing what “done” means.

### Worker

Worker must:

- read the task packet and relevant project instructions before editing;
- make the smallest coherent change that satisfies the acceptance criteria;
- avoid unrelated formatting, refactoring, or dependency upgrades;
- add or update tests when the task requires behavior changes;
- run targeted tests and report command, exit code, executed/passed/failed counts;
- record changed files, evidence, deviations, unexpected repository state, unresolved questions, Reviewer focus, and Memory candidates;
- stop and ask Chief when the task is ambiguous, under-scoped, or conflicts with project rules.

Worker may edit implementation, tests, and task result files inside the assigned scope. Worker must not silently redefine requirements, modify the Chief’s plan, or self-certify a task as passed.

### Reviewer

Reviewer must:

- start from the original task packet, not only the Worker summary;
- inspect the actual diff and relevant surrounding code;
- check every acceptance criterion;
- run targeted tests or reproduce the reported behavior;
- distinguish verified facts, inference, and suggestions;
- cite file paths, line numbers, commands, and observed output for findings;
- on `FAIL`, provide Findings, Evidence, Likely Root Cause, Recommended Solution, Affected Scope, Regression Risks, and Confidence;
- return exactly one verdict: `PASS`, `FAIL`, or `BLOCKED`.

Classify findings as `BLOCKER`, `MAJOR`, `MINOR`, or `QUESTION`. An inferential finding is not repair authorization: verify it first, then create a repair task only if the evidence supports it.

Reviewer may write review artifacts but must not edit implementation files or quietly fix the issue being reviewed.

## State and escalation

Use the following state sequence in `Workflow/STATE.json`:

```text
READY → EXECUTING → REVIEWING → PASSED
                         ↓
                      REPAIRING ↺
```

Move to `BLOCKED` or Chief escalation when any of these occurs:

- the same root cause remains after Chief-directed repair attempts;
- Worker and Reviewer still disagree after one evidence exchange;
- the proposed change exceeds the task scope or conflicts with the plan;
- a critical security, data-loss, compatibility, or architecture risk appears;
- required project information or external authority is missing.

Never solve a review loop by weakening the acceptance criteria without a recorded Chief decision.

## Project-local records

Keep policy and state separate:

- `AGENTS.md` is the durable rulebook: role boundaries, workflow protocol, evidence rules, artifact paths, and safety constraints.
- `Workflow/config.json` is the runtime configuration: declared Main and persistent Chief models, Worker and Reviewer models, Worker concurrency limit, thinking depth, and configuration timestamp.
- `MEMORY.md` is durable knowledge: project facts, confirmed decisions, important discoveries, known pitfalls, user constraints, durable risks, and approved Memory candidates.
- `Workflow/STATE.json` is current operational state; `Workflow/events.jsonl` is the routine runtime log; `Workflow/` contains detailed packets and reports.

Read [references/file-contract.md](references/file-contract.md) when deciding what belongs in either file. Use [references/AGENTS.template.md](references/AGENTS.template.md) and [references/MEMORY.template.md](references/MEMORY.template.md) when adapting the contract manually.

Record a completed action with:

```bash
python3 <skill-root>/scripts/record_workflow_event.py \
  --project-root <project-root> \
  --task-id <task-id> \
  --role Worker \
  --event-type worker_completed \
  --action "Implemented the bounded change" \
  --result "Targeted tests passed" \
  --evidence "Workflow/results/<task-id>.md" \
  --next-action "Reviewer to inspect the diff"
```

Use `scripts/validate_test_evidence.py` to reject `exit_code == 0` with `executed_tests == 0`. Use `scripts/validate_task_plan.py` for dependency, expected-write-scope, and review-stability signals, and `scripts/build_review_bundle.py` for bundle-first review context. These scripts provide guardrails; Main still decides runtime scheduling.

Do not store API keys, tokens, credentials, private personal data, or full command output containing secrets in either project file. Store concise summaries and pointers to safe artifacts.

## Completion gate

Declare the workflow complete only when:

- every acceptance criterion has a recorded result;
- the Reviewer has returned `PASS`;
- tests and other verification commands are recorded;
- unresolved risks and deviations are visible in `MEMORY.md`;
- the task ledger, work log, and decision records are up to date.
