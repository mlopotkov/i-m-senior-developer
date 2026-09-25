"""Run and verify the complete planner plugin eval suite."""

from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from eval_runner import EvalSuite, main  # noqa: E402


SUITE = EvalSuite(
    plugin_path="plugins/planner",
    expected_cases=frozenset(
        {
            "baseline-provider-limits",
            "feature-provider-contract",
            "idea-routing",
            "multi-step-input",
        }
    ),
    validated_paths=(
        "plugins/planner",
        "plugins/planner/commands",
        "plugins/planner/skills",
        "plugins/planner/agents",
    ),
    eval_flags=(
        "--ablation",
        "none",
        "--runs",
        "3",
        "--allow-tools",
        "Bash,Write",
        "--scaffold",
        "--no-publish",
        "--threshold",
        "1.0",
        "--model",
        "opus",
        "--judge-model",
        "haiku",
    ),
    default_max_cost_usd="6.00",
    results_root_variable="PLANNER_EVAL_RESULTS_ROOT",
)


if __name__ == "__main__":
    main(SUITE, "planner", REPO_ROOT)
