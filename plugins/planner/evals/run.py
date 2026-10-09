"""Run and verify the complete planner plugin eval suite."""

from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from baseline_delivery import DeliveryError, validate_baseline_runs  # noqa: E402
from eval_runner import EvalSuite, RunnerError, main  # noqa: E402
from feature_flow import FlowError, validate_feature_runs  # noqa: E402


def validate_full_trajectory(document, output_dir):
    try:
        validate_baseline_runs(document, output_dir)
    except (DeliveryError, OSError) as error:
        raise RunnerError(f"baseline delivery: {error}") from error
    try:
        validate_feature_runs(document, output_dir)
    except (FlowError, OSError) as error:
        raise RunnerError(f"feature trajectory: {error}") from error


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
        "--keep-temp",
        "--no-publish",
        "--threshold",
        "1.0",
        "--model",
        "opus",
        "--judge-model",
        "haiku",
    ),
    default_max_cost_usd="100.00",
    results_root_variable="PLANNER_EVAL_RESULTS_ROOT",
    full_trace_validator=validate_full_trajectory,
)


if __name__ == "__main__":
    main(SUITE, "planner", REPO_ROOT)
