from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"


class WorkflowScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.project = Path(tempfile.mkdtemp(prefix="chef-worker-reviewer-test-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.project, ignore_errors=True)

    def run_script(self, name: str, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.run(
            [sys.executable, str(SCRIPTS / name), *args],
            check=check,
            capture_output=True,
            text=True,
            env=environment,
        )

    def initialize(self) -> None:
        self.run_script(
            "init_project_workflow.py",
            "--project-root", str(self.project),
            "--main-model", "current-main-conversation",
            "--chief", "chief-owner", "--worker", "worker-owner", "--reviewer", "reviewer-owner",
            "--chief-model", "chief-model", "--worker-model", "worker-model", "--reviewer-model", "reviewer-model",
            "--max-worker-concurrency", "2", "--thinking-depth", "high",
        )

    def write_task(self, task_id: str = "T-001", scope: str = "src/a.py", dependencies: str = "None") -> None:
        task = self.project / "Workflow" / "tasks" / f"{task_id}.md"
        task.write_text(
            f"# {task_id}\n\n## Objective\nImplement the bounded task.\n\n## Context\nFixture.\n\n"
            f"## Dependencies\n{dependencies}\n\n## Scope\nImplement this task.\n\n## Out of Scope\nOther tasks.\n\n"
            f"## Relevant Files / Areas\n`{scope}`\n\n## Expected / Allowed Write Scope\n- `{scope}`\n\n"
            "## Implementation Guidance\nKeep the change bounded.\n\n## Constraints\nNone.\n\n## Acceptance Criteria\n- The task works.\n\n"
            "## Required Verification\n- Run the targeted test.\n\n## Reviewer Focus\nCheck the acceptance criterion.\n\n## Deliverables\nImplementation and evidence.\n",
            encoding="utf-8",
        )

    def record_event(self, task_id: str, event_type: str, role: str = "Reviewer", action: str = "review", result: str = "result", **extra: str) -> subprocess.CompletedProcess[str]:
        args = [
            "--project-root", str(self.project), "--task-id", task_id, "--role", role,
            "--action", action, "--result", result, "--event-type", event_type,
        ]
        for key, value in extra.items():
            args.extend([f"--{key.replace('_', '-')}", value])
        return self.run_script("record_workflow_event.py", *args)

    def test_initial_v14_artifacts_and_visible_directory(self) -> None:
        self.initialize()
        expected_files = {"PLAN.md", "MAIN_BRIEF.md", "STATE.json", "events.jsonl", "config.json", "manifest.json"}
        self.assertTrue(expected_files.issubset({path.name for path in (self.project / "Workflow").iterdir()}))
        self.assertTrue((self.project / "Workflow" / "review-bundles").is_dir())
        self.assertFalse((self.project / ".workflow").exists())
        self.assertEqual(json.loads((self.project / "Workflow" / "config.json").read_text())["version"], "1.4")

    def test_v13_config_is_readable(self) -> None:
        self.initialize()
        config_path = self.project / "Workflow" / "config.json"
        config = json.loads(config_path.read_text())
        config["version"] = "1.3"
        config["models"].pop("main")
        config_path.write_text(json.dumps(config), encoding="utf-8")
        result = self.run_script("init_project_workflow.py", "--project-root", str(self.project))
        self.assertEqual(result.returncode, 0)

    def test_formal_review_fail_only_increments_worker_failures(self) -> None:
        self.initialize()
        self.write_task()
        common = ("--project-root", str(self.project), "--task-id", "T-001", "--role", "Reviewer", "--action", "review", "--result", "result")
        self.run_script("record_workflow_event.py", *common, "--event-type", "review_passed")
        state_path = self.project / "Workflow" / "STATE.json"
        self.assertEqual(json.loads(state_path.read_text())["tasks"]["T-001"]["worker_failures"], 0)
        self.run_script("record_workflow_event.py", *common, "--event-type", "review_failed")
        self.assertEqual(json.loads(state_path.read_text())["tasks"]["T-001"]["worker_failures"], 1)
        self.run_script("record_workflow_event.py", *common, "--event-type", "review_failed")
        task_state = json.loads(state_path.read_text())["tasks"]["T-001"]
        self.assertEqual(task_state["worker_failures"], 2)
        self.assertTrue(task_state["expert_worker_required"])
        self.assertEqual(len((self.project / "Workflow" / "events.jsonl").read_text().splitlines()), 3)
        self.assertNotIn("review_failed", (self.project / "MEMORY.md").read_text())

    def test_review_failure_routes_first_to_chief_second_to_expert_and_expert_fail_to_chief(self) -> None:
        self.initialize()
        self.write_task()
        self.record_event("T-001", "review_failed")
        state_path = self.project / "Workflow" / "STATE.json"
        task_state = json.loads(state_path.read_text())["tasks"]["T-001"]
        self.assertEqual(task_state["worker_failures"], 1)
        self.assertTrue(task_state["chief_escalation_required"])
        self.assertFalse(task_state["expert_worker_required"])
        self.assertEqual(task_state["next_route"], "Chief")

        self.record_event("T-001", "decision_recorded", role="Chief", action="Decision Delta", result="REPAIR")
        self.record_event("T-001", "worker_dispatched", role="Main", action="dispatch normal worker", result="started")
        self.record_event("T-001", "review_failed")
        task_state = json.loads(state_path.read_text())["tasks"]["T-001"]
        self.assertEqual(task_state["worker_failures"], 2)
        self.assertFalse(task_state["chief_escalation_required"])
        self.assertTrue(task_state["expert_worker_required"])
        self.assertEqual(task_state["next_route"], "Expert Worker")

        self.record_event("T-001", "expert_worker_dispatched", role="Main", action="dispatch Expert Worker", result="started")
        task_state = json.loads(state_path.read_text())["tasks"]["T-001"]
        self.assertEqual(task_state["next_route"], "Reviewer")
        self.assertEqual(task_state["same_reviewer_policy"]["mode"], "same-logical-reviewer")
        self.assertTrue(task_state["same_reviewer_policy"]["session_preferred"])
        self.record_event("T-001", "review_failed")
        task_state = json.loads(state_path.read_text())["tasks"]["T-001"]
        self.assertTrue(task_state["chief_escalation_required"])
        self.assertFalse(task_state["expert_worker_required"])
        self.assertEqual(task_state["next_route"], "Chief")

    def test_second_fail_with_explicit_plan_issue_routes_to_chief(self) -> None:
        self.initialize()
        self.write_task()
        self.record_event("T-001", "review_failed")
        self.run_script(
            "record_workflow_event.py", "--project-root", str(self.project), "--task-id", "T-001",
            "--role", "Reviewer", "--action", "review", "--result", "plan issue", "--event-type", "review_failed",
            "--plan-level-issue",
        )
        task_state = json.loads((self.project / "Workflow" / "STATE.json").read_text())["tasks"]["T-001"]
        self.assertTrue(task_state["chief_escalation_required"])
        self.assertFalse(task_state["expert_worker_required"])
        self.assertTrue(task_state["plan_level_issue"])

    def test_review_pass_clears_repair_and_escalation_state(self) -> None:
        self.initialize()
        self.write_task()
        self.record_event("T-001", "review_failed")
        self.record_event("T-001", "review_failed")
        self.record_event("T-001", "review_passed")
        task_state = json.loads((self.project / "Workflow" / "STATE.json").read_text())["tasks"]["T-001"]
        self.assertEqual(task_state["status"], "PASSED")
        self.assertFalse(task_state["expert_worker_required"])
        self.assertFalse(task_state["chief_escalation_required"])
        self.assertEqual(task_state["next_route"], "Main")

    def test_workflow_status_aggregates_all_tasks(self) -> None:
        self.initialize()
        self.write_task("T-001", "src/a.py")
        self.write_task("T-002", "src/b.py")
        self.record_event("T-001", "review_passed")
        self.record_event("T-002", "task_started", role="Main", action="start", result="executing")
        state_path = self.project / "Workflow" / "STATE.json"
        self.assertNotEqual(json.loads(state_path.read_text())["workflow_status"], "PASSED")
        self.record_event("T-002", "review_started")
        self.assertNotEqual(json.loads(state_path.read_text())["workflow_status"], "PASSED")
        self.record_event("T-002", "review_passed")
        self.assertEqual(json.loads(state_path.read_text())["workflow_status"], "PASSED")

        self.write_task("T-003", "src/c.py")
        self.record_event("T-003", "review_failed")
        self.assertNotEqual(json.loads(state_path.read_text())["workflow_status"], "PASSED")
        self.record_event("T-003", "task_blocked", role="Main", action="block", result="blocked")
        self.assertEqual(json.loads(state_path.read_text())["workflow_status"], "BLOCKED")

    def test_workflow_status_does_not_let_pass_hide_repair(self) -> None:
        self.initialize()
        self.write_task("T-001", "src/a.py")
        self.write_task("T-002", "src/b.py")
        self.record_event("T-001", "review_failed")
        self.record_event("T-002", "review_passed")
        state = json.loads((self.project / "Workflow" / "STATE.json").read_text())
        self.assertEqual(state["tasks"]["T-001"]["status"], "REPAIRING")
        self.assertEqual(state["workflow_status"], "REPAIRING")

        self.write_task("T-003", "src/c.py")
        self.record_event("T-003", "task_blocked", role="Main", action="block", result="blocked")
        self.assertEqual(json.loads((self.project / "Workflow" / "STATE.json").read_text())["workflow_status"], "BLOCKED")

    def test_zero_tests_are_invalid(self) -> None:
        result = self.run_script("validate_test_evidence.py", "--exit-code", "0", "--executed-tests", "0", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("INVALID_TEST_EXECUTION", result.stdout)
        valid = self.run_script("validate_test_evidence.py", "--exit-code", "0", "--executed-tests", "1", "--passed-tests", "1")
        self.assertEqual(valid.stdout.strip(), "VALID_TEST_EVIDENCE")

    def test_dependency_and_review_stability_guardrails(self) -> None:
        self.initialize()
        self.write_task("T-001", "src/shared.py")
        self.write_task("T-002", "src/shared.py", "T-001")
        not_ready = self.run_script("validate_task_plan.py", "--project-root", str(self.project), "--task-id", "T-002", "--json", check=False)
        self.assertNotEqual(not_ready.returncode, 0)
        self.assertIn("dependency_not_ready", not_ready.stdout)
        conflict = self.run_script("validate_task_plan.py", "--project-root", str(self.project), "--reviewing-task", "T-001", "--candidate-task", "T-002", "--json", check=False)
        self.assertNotEqual(conflict.returncode, 0)
        self.assertIn("review_stability_conflict", conflict.stdout)
        stable = self.run_script(
            "validate_task_plan.py", "--project-root", str(self.project), "--reviewing-task", "T-001",
            "--candidate-task", "T-002", "--stable-review-snapshot", "--json",
        )
        self.assertEqual(stable.returncode, 0)

    def test_parallel_worker_pair_hard_blocks_overlapping_shared_scope(self) -> None:
        self.initialize()
        self.write_task("T-001", "src/shared.py")
        self.write_task("T-002", "src/shared.py")
        global_scan = self.run_script("validate_task_plan.py", "--project-root", str(self.project), "--json")
        self.assertIn("shared_write_scope", global_scan.stdout)
        parallel = self.run_script(
            "validate_task_plan.py", "--project-root", str(self.project), "--check-parallel", "T-001", "T-002", "--json", check=False,
        )
        self.assertNotEqual(parallel.returncode, 0)
        self.assertIn("parallel_worker_write_conflict", parallel.stdout)

        self.write_task("T-003", "src/module/")
        self.write_task("T-004", "src/module/a.py")
        parent_child = self.run_script(
            "validate_task_plan.py", "--project-root", str(self.project), "--check-parallel", "T-003", "T-004", "--json", check=False,
        )
        self.assertNotEqual(parent_child.returncode, 0)
        self.assertIn("parallel_worker_write_conflict", parent_child.stdout)

        self.write_task("T-005", "src/a.py")
        self.write_task("T-006", "src/b.py")
        disjoint = self.run_script(
            "validate_task_plan.py", "--project-root", str(self.project), "--check-parallel", "T-005", "T-006", "--json",
        )
        self.assertEqual(disjoint.returncode, 0)
        self.assertIn('"SAFE"', disjoint.stdout)

        isolated = self.run_script(
            "validate_task_plan.py", "--project-root", str(self.project), "--check-parallel", "T-001", "T-002",
            "--isolated-worktrees", "--json",
        )
        self.assertEqual(isolated.returncode, 0)

    def test_review_bundle_is_attempt_scoped_and_non_overwriting(self) -> None:
        self.initialize()
        self.write_task()
        result_path = self.project / "Workflow" / "results" / "T-001.md"
        result_path.write_text("# Worker Result\n\n## Status\nPASS\n", encoding="utf-8")
        self.run_script("build_review_bundle.py", "--project-root", str(self.project), "--task-id", "T-001", "--attempt", "1")
        bundle = self.project / "Workflow" / "review-bundles" / "T-001" / "1"
        self.assertTrue((bundle / "metadata.json").is_file())
        metadata = json.loads((bundle / "metadata.json").read_text())
        self.assertTrue(metadata["immutable"])
        self.assertIn("diff_source", metadata)
        self.assertIn("diff_patch", metadata["source_hashes"])
        self.assertEqual((bundle / "metadata.json").stat().st_mode & 0o222, 0)
        duplicate = self.run_script("build_review_bundle.py", "--project-root", str(self.project), "--task-id", "T-001", "--attempt", "1", check=False)
        self.assertNotEqual(duplicate.returncode, 0)

    def test_review_bundle_uses_explicit_revision_boundary(self) -> None:
        self.initialize()
        self.write_task()
        result_path = self.project / "Workflow" / "results" / "T-001.md"
        result_path.write_text("# Worker Result\n\n## Status\nPASS\n", encoding="utf-8")
        source = self.project / "src" / "a.py"
        source.parent.mkdir()
        source.write_text("before\n", encoding="utf-8")
        git_args = ["git", "-C", str(self.project)]
        subprocess.run(git_args + ["init", "-q"], check=True, capture_output=True, text=True)
        subprocess.run(git_args + ["add", "."], check=True, capture_output=True, text=True)
        subprocess.run(git_args + ["-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "base"], check=True, capture_output=True, text=True)
        source.write_text("after\n", encoding="utf-8")
        subprocess.run(git_args + ["add", "src/a.py"], check=True, capture_output=True, text=True)
        subprocess.run(git_args + ["-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "review"], check=True, capture_output=True, text=True)
        built = self.run_script(
            "build_review_bundle.py", "--project-root", str(self.project), "--task-id", "T-001", "--attempt", "1",
            "--base-revision", "HEAD^", "--review-revision", "HEAD",
        )
        self.assertEqual(built.returncode, 0)
        metadata = json.loads((self.project / "Workflow" / "review-bundles" / "T-001" / "1" / "metadata.json").read_text())
        self.assertEqual(metadata["diff_source"], "revision_boundary")
        self.assertEqual(metadata["stability_signal"], "SAFE")
        self.assertEqual(metadata["changed_files"], ["src/a.py"])

    def test_dirty_shared_worktree_with_other_active_task_blocks_bundle(self) -> None:
        self.initialize()
        self.write_task("T-001", "src/a.py")
        self.write_task("T-002", "src/b.py")
        result_path = self.project / "Workflow" / "results" / "T-001.md"
        result_path.write_text("# Worker Result\n\n## Status\nPASS\n", encoding="utf-8")
        (self.project / "src").mkdir()
        (self.project / "src" / "a.py").write_text("dirty\n", encoding="utf-8")
        self.record_event("T-002", "task_started", role="Main", action="start", result="executing")
        blocked = self.run_script("build_review_bundle.py", "--project-root", str(self.project), "--task-id", "T-001", check=False)
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn("UNSTABLE_REVIEW_DIFF", blocked.stdout)
        self.assertFalse((self.project / "Workflow" / "review-bundles" / "T-001" / "1").exists())

    def test_legacy_migration_preserves_backup(self) -> None:
        self.initialize()
        visible = self.project / "Workflow"
        legacy = self.project / ".workflow"
        shutil.move(visible, legacy)
        migrated = self.run_script("init_project_workflow.py", "--project-root", str(self.project), "--migrate-legacy")
        self.assertEqual(migrated.returncode, 0)
        self.assertTrue((self.project / "Workflow").is_dir())
        self.assertTrue(legacy.is_dir())

    def test_unmanaged_files_require_policy(self) -> None:
        (self.project / "AGENTS.md").write_text("user rules\n", encoding="utf-8")
        (self.project / "MEMORY.md").write_text("user memory\n", encoding="utf-8")
        blocked = self.run_script("init_project_workflow.py", "--project-root", str(self.project), check=False)
        self.assertNotEqual(blocked.returncode, 0)
        merged = self.run_script(
            "init_project_workflow.py", "--project-root", str(self.project), "--file-policy", "merge",
            "--chef-model", "chief-model", "--worker-model", "worker-model", "--reviewer-model", "reviewer-model",
            "--max-worker-concurrency", "1", "--thinking-depth", "medium",
        )
        self.assertEqual(merged.returncode, 0)
        self.assertIn("user rules", (self.project / "AGENTS.md").read_text())
        self.assertIn("user memory", (self.project / "MEMORY.md").read_text())


if __name__ == "__main__":
    unittest.main()
