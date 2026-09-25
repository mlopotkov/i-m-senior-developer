import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from eval_runner_fixtures import EvalRunnerTestCase, main  # noqa: E402


class SdlcEvalRunnerTest(EvalRunnerTestCase):
    runner_path = Path(__file__).with_name("run.py")
    plugin_path = "plugins/sdlc"
    eval_target = "."
    expected_cases = (
        "commit-range-coverage",
        "empty-target-coverage",
        "invalid-base-stop",
        "mined-guards-architect",
        "mined-guards-code-diff",
        "mined-guards-implementer",
        "mined-guards-prose-diff",
        "orchestrated-report-write",
        "working-tree-coverage",
    )
    validated_paths = (
        "plugins/sdlc",
        "plugins/sdlc/skills",
        "plugins/sdlc/agents",
    )
    eval_flags = (
        "--eval-dir",
        "plugins/sdlc/evals",
        "--ablation",
        "none",
        "--runs",
        "3",
        "--concurrency",
        "2",
        "--allow-tools",
        "Bash",
        "Write",
        "Edit",
        "--scaffold",
        "--no-publish",
        "--threshold",
        "1.0",
        "--model",
        "opus",
        "--judge-model",
        "haiku",
    )
    default_max_cost_usd = "38.00"
    results_root_variable = "SDLC_EVAL_RESULTS_ROOT"


if __name__ == "__main__":
    main()
