"""Run and verify the complete clarity-language plugin eval suite."""

from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from eval_runner import EvalSuite, main  # noqa: E402


SUITE = EvalSuite(
    plugin_path="plugins/clarity-language",
    expected_cases=frozenset(
        {
            "cancel-does-not-delete",
            "consumed-draft-collocation",
            "contract-literals-unchanged",
            "e2e-term-accepted",
            "exact-path-scope",
            "lease-mechanism-boundary",
            "matching-files-no-loaded-version",
            "modifier-scope-current-complete",
            "observed-delete-preserved",
        }
    ),
    validated_paths=(
        "plugins/clarity-language",
        "plugins/clarity-language/skills",
    ),
    eval_flags=(
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
    ),
    default_max_cost_usd="6.00",
    results_root_variable="CLARITY_LANGUAGE_EVAL_RESULTS_ROOT",
)


if __name__ == "__main__":
    main(SUITE, "clarity-language", REPO_ROOT)
