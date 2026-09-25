"""Shared release gate for plugin eval suites.

A plugin's `evals/run.py` states what its suite is — the cases it must contain,
the structure to validate, the CLI flags to run it with — and this module holds
the checks that must be identical for every plugin: the CLI version, the early
access gate, strict structural validation before any money is spent, and the
result contract that a zero exit code alone does not prove.
"""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any
import tempfile
import uuid


MINIMUM_CLAUDE_VERSION = "2.1.273"


class RunnerError(RuntimeError):
    pass


@dataclass(frozen=True)
class EvalSuite:
    """What distinguishes one plugin's release gate from another's."""

    plugin_path: str
    expected_cases: frozenset[str]
    validated_paths: tuple[str, ...]
    eval_flags: tuple[str, ...]
    default_max_cost_usd: str
    results_root_variable: str
    runs_per_case: int = 3
    # A plugin that declares dependencies loads only when they load too, and a
    # case may name plugins only under the target. Such a suite points the run
    # at the directory holding all of them and names its eval dir below it.
    eval_target: str = ""


def run_claude(
    claude_bin: str,
    arguments: list[str],
    cwd: Path,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            [claude_bin, *arguments],
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as error:
        raise RunnerError(f"Claude CLI not found: {claude_bin}") from error


def command_output(result: subprocess.CompletedProcess[str]) -> str:
    return "\n".join(
        part.strip() for part in (result.stdout, result.stderr) if part.strip()
    )


def version_key(version: str) -> tuple[int, ...]:
    parts = version.split(".")
    if not all(part.isdecimal() for part in parts):
        raise RunnerError(
            f"Claude Code version {version!r} could not be compared with the "
            f"required minimum {MINIMUM_CLAUDE_VERSION}: expected numbers "
            "separated by dots"
        )
    return tuple(int(part) for part in parts)


def require_claude_version(claude_bin: str, repo_root: Path) -> None:
    result = run_claude(claude_bin, ["--version"], repo_root)
    output = command_output(result)
    if result.returncode != 0:
        raise RunnerError(
            f"claude --version failed with code {result.returncode}: {output}"
        )
    actual = output.split(maxsplit=1)[0] if output else "<empty output>"
    if version_key(actual) < version_key(MINIMUM_CLAUDE_VERSION):
        raise RunnerError(
            "Claude Code is older than the eval contract allows: "
            f"needs {MINIMUM_CLAUDE_VERSION} or newer, got {actual}"
        )


def require_open_eval_gate(claude_bin: str) -> None:
    with tempfile.TemporaryDirectory(prefix="plugin-eval-gate-") as directory:
        result = run_claude(
            claude_bin, ["plugin", "eval", "--trust-plugin"], Path(directory)
        )
    output = command_output(result)
    if result.returncode == 1 and "No eval cases found" in output:
        return
    raise RunnerError(
        "claude plugin eval gate probe failed: "
        f"expected code 1 with 'No eval cases found', got code "
        f"{result.returncode}: {output}"
    )


def validate_plugin(claude_bin: str, repo_root: Path, suite: EvalSuite) -> None:
    for path in suite.validated_paths:
        result = run_claude(
            claude_bin,
            ["plugin", "validate", path, "--strict"],
            repo_root,
        )
        if result.returncode != 0:
            raise RunnerError(
                f"plugin validation failed for {path} with code "
                f"{result.returncode}: {command_output(result)}"
            )


def fresh_output_path(results_root: Path) -> Path:
    results_root.mkdir(parents=True, exist_ok=True)
    for _ in range(10):
        candidate = results_root / f"run-{uuid.uuid4().hex}"
        if not candidate.exists():
            return candidate
    raise RunnerError(f"could not allocate a fresh output path under {results_root}")


def eval_arguments(
    suite: EvalSuite, max_cost_usd: str, output_dir: Path
) -> list[str]:
    return [
        "plugin",
        "eval",
        suite.eval_target or suite.plugin_path,
        "--trust-plugin",
        *suite.eval_flags,
        "--max-cost-usd",
        max_cost_usd,
        "--output-dir",
        str(output_dir),
    ]


def run_eval(
    claude_bin: str,
    repo_root: Path,
    suite: EvalSuite,
    max_cost_usd: str,
    output_dir: Path,
) -> None:
    result = run_claude(
        claude_bin,
        eval_arguments(suite, max_cost_usd, output_dir),
        repo_root,
    )
    if result.returncode != 0:
        raise RunnerError(
            f"claude plugin eval failed with code {result.returncode}: "
            f"{command_output(result)}"
        )


def require_mapping(value: object, location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RunnerError(f"{location} must be a JSON object")
    return value


def require_list(value: object, location: str) -> list[Any]:
    if not isinstance(value, list):
        raise RunnerError(f"{location} must be a JSON array")
    return value


def require_one(value: object, location: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != 1:
        raise RunnerError(f"{location} must equal 1, got {value!r}")


def require_top_level(result: dict[str, Any], suite: EvalSuite) -> None:
    if type(result.get("schemaVersion")) is not int or result["schemaVersion"] != 1:
        raise RunnerError("schemaVersion must be integer 1")
    if result.get("partial") is not False:
        raise RunnerError("partial must be false")
    aggregates = require_mapping(result.get("aggregates"), "aggregates")
    expected_case_count = len(suite.expected_cases)
    if aggregates.get("casesTotal") != expected_case_count:
        raise RunnerError(f"aggregates.casesTotal must equal {expected_case_count}")
    if aggregates.get("casesPassed") != expected_case_count:
        raise RunnerError(f"aggregates.casesPassed must equal {expected_case_count}")
    require_one(aggregates.get("overallScore"), "aggregates.overallScore")


def indexed_cases(
    result: dict[str, Any], suite: EvalSuite
) -> dict[str, dict[str, Any]]:
    cases = require_list(result.get("cases"), "cases")
    indexed: dict[str, dict[str, Any]] = {}
    for index, value in enumerate(cases):
        case = require_mapping(value, f"cases[{index}]")
        name = case.get("name")
        if not isinstance(name, str):
            raise RunnerError(f"cases[{index}].name must be a string")
        if name in indexed:
            raise RunnerError(f"duplicate eval case: {name}")
        indexed[name] = case
    actual = set(indexed)
    if actual != set(suite.expected_cases):
        missing = ", ".join(sorted(suite.expected_cases - actual)) or "none"
        unexpected = ", ".join(sorted(actual - suite.expected_cases)) or "none"
        raise RunnerError(
            f"cases must match the expected set; missing: {missing}; "
            f"unexpected: {unexpected}"
        )
    return indexed


def require_run(run: object, location: str) -> None:
    value = require_mapping(run, location)
    if value.get("passed") is not True:
        raise RunnerError(f"{location}.passed must be true")
    require_one(value.get("score"), f"{location}.score")
    if value.get("skippedPaidGraders") is not False:
        raise RunnerError(f"{location}.skippedPaidGraders must be false")


def require_case(case: dict[str, Any], name: str, suite: EvalSuite) -> None:
    aggregates = require_mapping(case.get("aggregates"), f"case {name}.aggregates")
    require_one(aggregates.get("score"), f"case {name}.aggregates.score")
    arms = require_mapping(case.get("arms"), f"case {name}.arms")
    runs = require_list(arms.get("with"), f"case {name}.arms.with")
    if len(runs) != suite.runs_per_case:
        raise RunnerError(
            f"case {name}.arms.with must contain exactly "
            f"{suite.runs_per_case} runs, got {len(runs)}"
        )
    for index, run in enumerate(runs):
        require_run(run, f"case {name}.arms.with[{index}]")


def validate_result(result: object, suite: EvalSuite) -> tuple[object, int]:
    document = require_mapping(result, "aggregate-result.json")
    cases = indexed_cases(document, suite)
    require_top_level(document, suite)
    for name, case in cases.items():
        require_case(case, name, suite)
    cost_usd = document.get("costUsd")
    if isinstance(cost_usd, bool) or not isinstance(cost_usd, (int, float)):
        raise RunnerError("costUsd must be a JSON number")
    return cost_usd, len(cases)


def load_result(output_dir: Path) -> object:
    aggregate_path = output_dir / "aggregate-result.json"
    report_path = output_dir / "report.html"
    if not aggregate_path.is_file():
        raise RunnerError(f"missing aggregate-result.json in {output_dir}")
    if not report_path.is_file():
        raise RunnerError(f"missing report.html in {output_dir}")
    try:
        return json.loads(aggregate_path.read_text())
    except json.JSONDecodeError as error:
        raise RunnerError(
            f"aggregate-result.json must contain valid JSON: {error}"
        ) from error


def run_suite(suite: EvalSuite, arguments: list[str], repo_root: Path) -> int:
    if arguments:
        raise RunnerError("this runner does not accept arguments")
    claude_bin = os.environ.get("CLAUDE_BIN", "claude")
    results_root = Path(
        os.environ.get(
            suite.results_root_variable,
            str(repo_root / suite.plugin_path / "evals/results"),
        )
    ).expanduser()
    max_cost_usd = os.environ.get("MAX_COST_USD", suite.default_max_cost_usd)

    require_claude_version(claude_bin, repo_root)
    require_open_eval_gate(claude_bin)
    validate_plugin(claude_bin, repo_root, suite)
    output_dir = fresh_output_path(results_root)
    run_eval(claude_bin, repo_root, suite, max_cost_usd, output_dir)
    cost_usd, case_count = validate_result(load_result(output_dir), suite)
    print(f"OK: output={output_dir} costUsd={cost_usd} cases={case_count}")
    return 0


def main(suite: EvalSuite, name: str, repo_root: Path) -> None:
    try:
        raise SystemExit(run_suite(suite, sys.argv[1:], repo_root))
    except RunnerError as error:
        print(f"{name} eval runner: {error}", file=sys.stderr)
        raise SystemExit(1)
