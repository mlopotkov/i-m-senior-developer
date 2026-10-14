"""Run and verify the complete sdlc plugin eval suite."""

from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from eval_runner import EvalSuite, main  # noqa: E402


SUITE = EvalSuite(
    plugin_path="plugins/sdlc",
    expected_cases=frozenset(
        {
            "commit-range-coverage",
            "empty-target-coverage",
            "invalid-base-stop",
            "mined-guards-architect",
            "mined-guards-code-diff",
            "mined-guards-implementer",
            "mined-guards-prose-diff",
            "orchestrated-report-write",
            "working-tree-coverage",
        }
    ),
    validated_paths=(
        "plugins/sdlc",
        "plugins/sdlc/skills",
        "plugins/sdlc/agents",
    ),
    # sdlc loads only together with tdd-master and functional-clarity: a plugin
    # whose declared dependency is absent is demoted, and the roles then answer
    # `Unknown skill`. The run is aimed at the repository root so all three are
    # under the containment root and the cases may name them.
    eval_target=".",
    eval_flags=(
        "--eval-dir",
        "plugins/sdlc/evals",
        "--ablation",
        "none",
        "--runs",
        "3",
        "--concurrency",
        "2",
        # Кейсам нужны разные инструменты: ревьюеру Bash, архитектору Write,
        # реализатору оба. Список выдаётся общий, а сужает его каждый кейс
        # своим allowed_tools. Здесь перечислены только гейтящиеся оператором
        # инструменты; Agent к ним не относится и запрашивается самим кейсом.
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
    ),
    default_max_cost_usd="100.00",
    results_root_variable="SDLC_EVAL_RESULTS_ROOT",
)


if __name__ == "__main__":
    main(SUITE, "sdlc", REPO_ROOT)
