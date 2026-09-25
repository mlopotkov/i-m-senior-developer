import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from eval_runner_fixtures import EvalRunnerTestCase, main  # noqa: E402


class ClarityLanguageEvalRunnerTest(EvalRunnerTestCase):
    runner_path = Path(__file__).with_name("run.py")
    plugin_path = "plugins/clarity-language"
    expected_cases = (
        "cancel-does-not-delete",
        "consumed-draft-collocation",
        "contract-literals-unchanged",
        "e2e-term-accepted",
        "exact-path-scope",
        "lease-mechanism-boundary",
        "matching-files-no-loaded-version",
        "modifier-scope-current-complete",
        "observed-delete-preserved",
    )
    validated_paths = (
        "plugins/clarity-language",
        "plugins/clarity-language/skills",
    )
    eval_flags = (
        "--ablation",
        "none",
        "--runs",
        "3",
        "--no-scaffold",
        "--no-publish",
        "--threshold",
        "1.0",
        "--model",
        "opus",
        "--judge-model",
        "haiku",
    )
    default_max_cost_usd = "6.00"
    results_root_variable = "CLARITY_LANGUAGE_EVAL_RESULTS_ROOT"


if __name__ == "__main__":
    main()
