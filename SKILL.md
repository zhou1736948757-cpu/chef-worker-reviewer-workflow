---
name: chef-worker-reviewer-workflow
description: Orchestrate a bounded Chief (also called Chef, embodied by the current main conversation) / Worker / Reviewer workflow for project tasks, including first-run model selection, Worker concurrency, and thinking-depth configuration. Use when a task needs multi-agent planning and implementation, independent review, repeatable state tracking, repair and escalation loops, or a project folder should be initialized with durable AGENTS.md, MEMORY.md, and .workflow records.
---

# Chief / Worker / Reviewer Workflow

Use this skill to run a task as a small, auditable production line. Treat “Chef” as an alias for “Chief” unless the user defines a different role.

## Operating model

Keep three concerns separate:

- Chief/Chef is the current main conversation model. It owns the objective, scope, acceptance criteria, task routing, decisions, and escalation.
- Worker owns implementation and verification inside one bounded task.
- Reviewer owns independent quality judgment and evidence collection; Reviewer does not edit implementation files.

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

## First-run setup (mandatory)

Before creating `AGENTS.md`, `MEMORY.md`, or dispatching any task, inspect `.workflow/config.json`.

If it does not exist, ask the user these five questions and wait for answers:

1. Which exact model should be the main conversation model and therefore serve as Chief/Chef?
2. Which exact model should run as Worker?
3. Which exact model should run as Reviewer?
4. What is the maximum number of Workers allowed to run concurrently?
5. What default thinking depth should all three roles use? Accept only a depth supported by the selected harness, such as `low`, `medium`, `high`, or `xhigh`.

Give role-oriented guidance while asking: choose the strongest planning model for Chief, a fast tool-capable model for Worker, and an independent model for Reviewer. Do not silently invent a model, concurrency limit, or thinking depth. If the harness exposes a model or reasoning catalog, validate the answers against it; otherwise preserve the exact user-provided identifiers and report that runtime support still needs verification.

Persist the answers in `.workflow/config.json` using this shape:

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

On later invocations, read and display this configuration briefly instead of asking again. Ask the five questions again only when the user explicitly requests reconfiguration. Record configuration changes in `MEMORY.md` before dispatching new work. Do not change models, concurrency, or thinking depth halfway through an active task without a Chief decision.

## Chef runtime identity and task-start reminder

Treat Chef as the controller embodied by the current main conversation. Do not spawn a separate Chef subagent for routine planning or arbitration. Only Worker and Reviewer are delegated roles.

At the beginning of every task, before creating the task packet or dispatching a Worker, remind the user:

> 提醒：本工作流中的 Chef 是当前主对话模型，负责规划、分工、决策和最终协调；Worker 负责执行，Reviewer 负责独立审核。

Include the configured Chef model from `.workflow/config.json`. If the harness exposes the actual current main-conversation model, include it and say whether it matches the configuration. If the harness cannot expose actual routing, state that the configured Chef model is the declared identity and that upstream routing is not independently verified. Never present a local configuration value as proof of the final upstream model.

If the observable current main-conversation model differs from the configured Chef model, pause before dispatching and ask the user whether to switch the main conversation model or explicitly reconfigure the workflow. Do not silently run a different Chef model.

## Start a workflow

1. Identify the project root. Prefer the repository root when `git rev-parse --show-toplevel` succeeds; otherwise use the requested project directory or current working directory.
2. Read existing project instructions before changing anything, especially `AGENTS.md`, `MEMORY.md`, and any nearer directory-level instructions.
3. Run the pre-generation file check above. Resolve any unmanaged-file choice before creating or updating either file.
4. Complete the first-run setup above. Then initialize the project-local contract with the bundled script:

   ```bash
   python3 <skill-root>/scripts/init_project_workflow.py \
     --project-root <project-root> \
     --chief <chief-owner> \
     --worker <worker-owner> \
     --reviewer <reviewer-owner> \
     --chef-model <chief-model-id> \
     --worker-model <worker-model-id> \
     --reviewer-model <reviewer-model-id> \
     --max-worker-concurrency <positive-integer> \
     --thinking-depth <supported-depth>
   ```

   The script writes `.workflow/config.json`, creates or updates only the managed workflow section of `AGENTS.md`, creates `MEMORY.md` when absent, preserves existing user content, and creates `.workflow/` packet directories. On a later run, omit the configuration flags to reuse the saved configuration; pass `--reconfigure` together with all five flags only after explicit user approval. It never replaces an existing project memory file wholesale.

5. Emit the Chef task-start reminder above, including configured-versus-observed model status.
6. Create a task packet at `.workflow/tasks/<task-id>.md` before implementation. Include the objective, scope, exclusions, acceptance criteria, test commands, constraints, dependencies, risks, and deliverables.
7. Dispatch one Worker per bounded task. Allow parallel Workers only when their file and dependency scopes do not overlap, and never exceed `max_worker_concurrency` from `.workflow/config.json`.
8. Require the Worker to write a result at `.workflow/results/<task-id>.md` containing changed files, commands run, results, evidence pointers, deviations, and unresolved questions.
9. Send the original task packet, the actual diff, and the Worker result to a fresh Reviewer context. Require a report at `.workflow/reviews/<task-id>-r<N>.md`.
10. On `PASS`, update `MEMORY.md` and close the task. On `FAIL`, create a bounded repair task and run the Worker–Reviewer loop again. On `BLOCKED`, or after three repairs with the same root cause, stop and make a Chief decision in `.workflow/decisions/`.

If the harness cannot create subagents, simulate the same separation in distinct phases and still persist the task, result, and review artifacts.

When dispatching, pass Worker and Reviewer their configured models and the configured `thinking_depth`; keep Chef in the current main conversation. Treat a harness rejection as a configuration error; stop and ask whether to reconfigure instead of silently falling back to another model or depth.

## Role contracts

### Chief

Chief must:

- convert the user goal into bounded tasks;
- define observable acceptance criteria and verification commands;
- state in-scope and out-of-scope files or behavior;
- identify dependencies, risks, and decisions that require authority;
- maintain the task ledger and current workflow state in `MEMORY.md`;
- resolve Worker–Reviewer conflicts with evidence;
- stop scope expansion, repeated failure, or architectural conflict and escalate.

Chief may change the plan and write task/decision records. Chief should not perform routine implementation. If Chief makes an emergency code change, route that change through the same Reviewer gate.

Chief is done with planning only when a Worker can execute without guessing what “done” means.

### Worker

Worker must:

- read the task packet and relevant project instructions before editing;
- make the smallest coherent change that satisfies the acceptance criteria;
- avoid unrelated formatting, refactoring, or dependency upgrades;
- add or update tests when the task requires behavior changes;
- run the specified tests and report actual results;
- record changed files, evidence, deviations, and unresolved questions;
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
- return exactly one verdict: `PASS`, `FAIL`, or `BLOCKED`.

Classify findings as `BLOCKER`, `MAJOR`, `MINOR`, or `QUESTION`. An inferential finding is not repair authorization: verify it first, then create a repair task only if the evidence supports it.

Reviewer may write review artifacts but must not edit implementation files or quietly fix the issue being reviewed.

## State and escalation

Use the following state sequence:

```text
READY → EXECUTING → REVIEWING → PASSED
                         ↓
                      REPAIRING ↺
```

Move to `BLOCKED` or Chief escalation when any of these occurs:

- the same root cause survives three repair attempts;
- Worker and Reviewer still disagree after one evidence exchange;
- the proposed change exceeds the task scope or conflicts with the plan;
- a critical security, data-loss, compatibility, or architecture risk appears;
- required project information or external authority is missing.

Never solve a review loop by weakening the acceptance criteria without a recorded Chief decision.

## Project-local records

Keep policy and state separate:

- `AGENTS.md` is the durable rulebook: role boundaries, workflow protocol, evidence rules, artifact paths, and safety constraints.
- `.workflow/config.json` is the runtime configuration: declared main-conversation Chef model, Worker and Reviewer models, Worker concurrency limit, thinking depth, and configuration timestamp.
- `MEMORY.md` is the durable ledger: role assignments, runtime configuration summary, current state, task history, decisions, work log, review findings, risks, and follow-ups.
- `.workflow/` contains detailed packets and reports so `MEMORY.md` stays concise and traceable.

Read [references/file-contract.md](references/file-contract.md) when deciding what belongs in either file. Use [references/AGENTS.template.md](references/AGENTS.template.md) and [references/MEMORY.template.md](references/MEMORY.template.md) when adapting the contract manually.

Record a completed action with:

```bash
python3 <skill-root>/scripts/record_workflow_event.py \
  --project-root <project-root> \
  --task-id <task-id> \
  --role Worker \
  --action "Implemented the bounded change" \
  --result "Targeted tests passed" \
  --evidence ".workflow/results/<task-id>.md" \
  --next-action "Reviewer to inspect the diff"
```

Do not store API keys, tokens, credentials, private personal data, or full command output containing secrets in either project file. Store concise summaries and pointers to safe artifacts.

## Completion gate

Declare the workflow complete only when:

- every acceptance criterion has a recorded result;
- the Reviewer has returned `PASS`;
- tests and other verification commands are recorded;
- unresolved risks and deviations are visible in `MEMORY.md`;
- the task ledger, work log, and decision records are up to date.
