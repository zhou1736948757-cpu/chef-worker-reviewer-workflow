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
            "--chef-model", "chief-model", "--worker-model", "worker-model", "--reviewer-model", "reviewer-model",
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
        duplicate = self.run_script("build_review_bundle.py", "--project-root", str(self.project), "--task-id", "T-001", "--attempt", "1", check=False)
        self.assertNotEqual(duplicate.returncode, 0)

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
