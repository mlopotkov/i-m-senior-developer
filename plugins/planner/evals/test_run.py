import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from eval_runner_fixtures import EvalRunnerTestCase, main  # noqa: E402


class PlannerEvalRunnerTest(EvalRunnerTestCase):
    runner_path = Path(__file__).with_name("run.py")
    plugin_path = "plugins/planner"
    expected_cases = (
        "baseline-provider-limits",
        "feature-provider-contract",
        "idea-routing",
        "multi-step-input",
    )
    validated_paths = (
        "plugins/planner",
        "plugins/planner/commands",
        "plugins/planner/skills",
        "plugins/planner/agents",
    )
    eval_flags = (
        "--ablation",
        "none",
        "--runs",
        "3",
        "--allow-tools",
        "Bash,Write",
        "--scaffold",
        "--keep-temp",
        "--no-publish",
        "--threshold",
        "1.0",
        "--model",
        "opus",
        "--judge-model",
        "haiku",
    )
    default_max_cost_usd = "100.00"
    results_root_variable = "PLANNER_EVAL_RESULTS_ROOT"
    trace_fixture = Path(__file__).with_name("test_baseline_delivery.py")

    def test__runner__denied_baseline_skill__cannot_report_success(self):
        result = self.run_runner(extra_env={"FAKE_CLAUDE_TRACE_VARIANT": "denied-skill"})
        self.assertEqual(result.returncode, 1)
        self.assertIn("baseline delivery", result.stderr)
        self.assertIn("planner:product-baseline", result.stderr)

    def test__runner__different_helper_source__cannot_report_success(self):
        result = self.run_runner(extra_env={"FAKE_CLAUDE_TRACE_VARIANT": "fake-helper"})
        self.assertEqual(result.returncode, 1)
        self.assertIn("helper source", result.stderr)

    def test__runner__altered_provider_response__cannot_report_success(self):
        result = self.run_runner(extra_env={"FAKE_CLAUDE_TRACE_VARIANT": "changed-response"})
        self.assertEqual(result.returncode, 1)
        self.assertIn("differs from provider", result.stderr)


if __name__ == "__main__":
    main()
