"""Shared behaviour tests for plugin eval release gates.

A plugin's `evals/test_run.py` declares its suite and inherits these cases, so
that the gate of every plugin is held to the same observed behaviour: no money
before the version, gate and structure checks pass, and a result that only a
complete, non-partial, fully scored run can satisfy.
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
from typing import TypedDict, cast
import unittest


class ClaudeCall(TypedDict):
    argv: list[str]
    cwd: str


FAKE_CLAUDE = r'''#!/usr/bin/env python3
import json
import os
import runpy
from pathlib import Path
import sys


CASE_NAMES = json.loads(os.environ["FAKE_CLAUDE_CASES"])
RUNS_PER_CASE = int(os.environ.get("FAKE_CLAUDE_RUNS", "3"))


def log_call(argv):
    log_path = Path(os.environ["FAKE_CLAUDE_LOG"])
    with log_path.open("a") as stream:
        stream.write(json.dumps({"argv": argv, "cwd": os.getcwd()}) + "\n")


def valid_result():
    cases = []
    for case_index, case_name in enumerate(CASE_NAMES):
        runs = [
            {
                "passed": True,
                "score": 1,
                "skippedPaidGraders": False,
                # Наблюдённая форма: повтор может нести сообщение об ошибке и
                # всё равно быть зачтённым, если счёт и признак прохождения
                # держатся. Гейт судит по ним, а не по наличию сообщения.
                "error": (
                    "AskUserQuestion is unavailable in headless mode"
                    if case_index == 0 and run_index == 0
                    else None
                ),
            }
            for run_index in range(RUNS_PER_CASE)
        ]
        cases.append({
            "name": case_name,
            "aggregates": {"score": 1},
            "arms": {"with": runs},
        })
    return {
        "schemaVersion": 1,
        "costUsd": 0.42,
        "partial": False,
        "cases": cases,
        "aggregates": {
            "casesTotal": len(CASE_NAMES),
            "casesPassed": len(CASE_NAMES),
            "overallScore": 1,
        },
    }


def write_fixture(output_dir, fixture):
    if output_dir.exists():
        print(f"output directory already exists: {output_dir}", file=sys.stderr)
        raise SystemExit(90)
    output_dir.mkdir(parents=True)
    result = valid_result()
    builder = os.environ.get("FAKE_CLAUDE_TRACE_BUILDER")
    if builder:
        sys.path.insert(0, str(Path(builder).parent))
        module = runpy.run_path(builder)
        result = module["attach_traces"](result, output_dir, os.environ.get("FAKE_CLAUDE_TRACE_VARIANT", "valid"))
    if fixture == "partial":
        result["partial"] = True
    elif fixture == "missing-case":
        result["cases"].pop()
        case_count = len(result["cases"])
        result["aggregates"]["casesTotal"] = case_count
        result["aggregates"]["casesPassed"] = case_count
    elif fixture == "one-run-short":
        result["cases"][0]["arms"]["with"].pop()
    elif fixture == "skipped-paid-graders":
        result["cases"][0]["arms"]["with"][0]["skippedPaidGraders"] = True

    aggregate = output_dir / "aggregate-result.json"
    if fixture == "broken-json":
        aggregate.write_text("{broken")
    elif fixture != "missing-json":
        aggregate.write_text(json.dumps(result))
    if fixture != "missing-report":
        (output_dir / "report.html").write_text("<html>report</html>")


argv = sys.argv[1:]
log_call(argv)

if argv == ["--version"]:
    print(os.environ.get("FAKE_CLAUDE_VERSION", "2.1.273 (Claude Code)"))
    raise SystemExit(0)

if argv == ["plugin", "eval", "--trust-plugin"]:
    gate = os.environ.get("FAKE_CLAUDE_GATE", "open")
    if gate == "open":
        print("No eval cases found", file=sys.stderr)
        raise SystemExit(1)
    if gate == "closed":
        print("`plugin eval` is currently in early access", file=sys.stderr)
        raise SystemExit(1)
    print("unexpected gate response", file=sys.stderr)
    raise SystemExit(0)

if len(argv) == 4 and argv[:2] == ["plugin", "validate"] and argv[3] == "--strict":
    raise SystemExit(0)

if argv[:2] == ["plugin", "eval"] and argv[2] == os.environ["FAKE_CLAUDE_PLUGIN"]:
    exit_code = int(os.environ.get("FAKE_CLAUDE_EVAL_EXIT", "0"))
    if exit_code:
        print(f"eval stopped with code {exit_code}", file=sys.stderr)
        raise SystemExit(exit_code)
    output_dir = Path(argv[argv.index("--output-dir") + 1])
    write_fixture(output_dir, os.environ.get("FAKE_CLAUDE_FIXTURE", "valid"))
    raise SystemExit(0)

print(f"unsupported fake invocation: {argv}", file=sys.stderr)
raise SystemExit(91)
'''


class EvalRunnerTestCase(unittest.TestCase):
    """Behaviour every plugin release gate shares.

    A plugin test module sets the class attributes below; leaving
    `runner_path` unset keeps this base class itself out of the run.
    """

    runner_path: Path | None = None
    plugin_path: str = ""
    # The path the run is aimed at, when it is not the plugin directory itself.
    eval_target: str = ""
    expected_cases: tuple[str, ...] = ()
    validated_paths: tuple[str, ...] = ()
    eval_flags: tuple[str, ...] = ()
    default_max_cost_usd: str = ""
    results_root_variable: str = ""
    runs_per_case: int = 3
    trace_fixture: Path | None = None

    @classmethod
    def setUpClass(cls) -> None:
        if cls.runner_path is None:
            raise unittest.SkipTest("base class carries no runner")

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.repo_root = Path(__file__).resolve().parents[1]
        self.foreign_cwd = self.root / "foreign-cwd"
        self.foreign_cwd.mkdir()
        self.results_root = self.root / "results"
        self.log_path = self.root / "claude-calls.jsonl"
        self.fake_claude = self.root / "fake-claude"
        self.fake_claude.write_text(textwrap.dedent(FAKE_CLAUDE))
        self.fake_claude.chmod(0o755)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_runner(
        self,
        *args: str,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update(
            {
                "CLAUDE_BIN": str(self.fake_claude),
                "FAKE_CLAUDE_LOG": str(self.log_path),
                "FAKE_CLAUDE_CASES": json.dumps(list(self.expected_cases)),
                "FAKE_CLAUDE_PLUGIN": self.eval_target or self.plugin_path,
                "FAKE_CLAUDE_RUNS": str(self.runs_per_case),
                self.results_root_variable: str(self.results_root),
            }
        )
        env.pop("MAX_COST_USD", None)
        if self.trace_fixture is not None:
            env["FAKE_CLAUDE_TRACE_BUILDER"] = str(self.trace_fixture)
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [sys.executable, str(self.runner_path), *args],
            cwd=self.foreign_cwd,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def calls(self) -> list[ClaudeCall]:
        if not self.log_path.exists():
            return []
        return [
            cast(ClaudeCall, json.loads(line))
            for line in self.log_path.read_text().splitlines()
        ]

    def actual_eval_call(self) -> ClaudeCall:
        return next(
            call
            for call in self.calls()
            if call["argv"][:2] == ["plugin", "eval"]
            and len(call["argv"]) > 2
            and call["argv"][2] == (self.eval_target or self.plugin_path)
        )

    def test__runner__valid_eval__runs_preflight_and_reports_success(self) -> None:
        result = self.run_runner()

        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()
        self.assertEqual(calls[0]["argv"], ["--version"])
        self.assertEqual(calls[1]["argv"], ["plugin", "eval", "--trust-plugin"])
        self.assertNotEqual(calls[1]["cwd"], str(self.foreign_cwd))

        expected_validations = [
            ["plugin", "validate", path, "--strict"] for path in self.validated_paths
        ]
        validations = [
            call for call in calls if call["argv"][:2] == ["plugin", "validate"]
        ]
        self.assertEqual([call["argv"] for call in validations], expected_validations)
        self.assertEqual({call["cwd"] for call in validations}, {str(self.repo_root)})

        actual_eval = self.actual_eval_call()
        argv = actual_eval["argv"]
        output_dir = Path(argv[-1])
        self.assertEqual(
            argv,
            [
                "plugin",
                "eval",
                self.eval_target or self.plugin_path,
                "--trust-plugin",
                *self.eval_flags,
                "--max-cost-usd",
                self.default_max_cost_usd,
                "--output-dir",
                str(output_dir),
            ],
        )
        self.assertEqual(actual_eval["cwd"], str(self.repo_root))
        self.assertEqual(output_dir.parent, self.results_root)
        self.assertTrue((output_dir / "aggregate-result.json").is_file())
        self.assertTrue((output_dir / "report.html").is_file())
        self.assertIn(str(output_dir), result.stdout)
        self.assertIn("costUsd=0.42", result.stdout)
        self.assertIn(f"cases={len(self.expected_cases)}", result.stdout)
        self.assertEqual(result.stderr, "")

    def test__runner__invalid_result_fixture__fails_with_reason(self) -> None:
        cases = (
            ("partial", "partial"),
            # Фикстура снимает последний случай, поэтому ожидание берётся из
            # состава: при правке набора имя не должно отставать молча.
            ("missing-case", self.expected_cases[-1]),
            ("one-run-short", f"exactly {self.runs_per_case}"),
            ("skipped-paid-graders", "skippedPaidGraders"),
            ("broken-json", "valid JSON"),
            ("missing-json", "aggregate-result.json"),
            ("missing-report", "report.html"),
        )

        for fixture, expected_error in cases:
            with self.subTest(fixture=fixture):
                self.log_path.unlink(missing_ok=True)

                result = self.run_runner(extra_env={"FAKE_CLAUDE_FIXTURE": fixture})

                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected_error, result.stderr)

    def test__runner__version_at_or_above_minimum__runs_the_eval(self) -> None:
        for version in ("2.1.273", "2.1.1000", "2.2.0", "3.0.0"):
            with self.subTest(version=version):
                self.log_path.unlink(missing_ok=True)

                result = self.run_runner(
                    extra_env={"FAKE_CLAUDE_VERSION": f"{version} (Claude Code)"}
                )

                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.actual_eval_call()["cwd"], str(self.repo_root))

    def test__runner__version_below_minimum__fails_before_gate(self) -> None:
        for version in ("2.1.272", "2.1.267", "2.1.234", "2.1.99", "2.1", "2.0.999", "1.9.9"):
            with self.subTest(version=version):
                self.log_path.unlink(missing_ok=True)

                result = self.run_runner(
                    extra_env={"FAKE_CLAUDE_VERSION": f"{version} (Claude Code)"}
                )

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("2.1.273", result.stderr)
                self.assertIn(version, result.stderr)
                self.assertEqual(
                    [call["argv"] for call in self.calls()], [["--version"]]
                )
                self.assertEqual(list(self.results_root.glob("*")), [])

    def test__runner__uncomparable_version__fails_before_gate(self) -> None:
        for version in ("nonsense", "2.1.x", "2.1.4-beta.1", ""):
            with self.subTest(version=version):
                self.log_path.unlink(missing_ok=True)

                result = self.run_runner(extra_env={"FAKE_CLAUDE_VERSION": version})

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("could not be compared", result.stderr)
                self.assertEqual(
                    [call["argv"] for call in self.calls()], [["--version"]]
                )
                self.assertEqual(list(self.results_root.glob("*")), [])

    def test__runner__closed_gate__fails_before_validation(self) -> None:
        result = self.run_runner(extra_env={"FAKE_CLAUDE_GATE": "closed"})

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("early access", result.stderr)
        self.assertEqual(
            [call["argv"] for call in self.calls()],
            [["--version"], ["plugin", "eval", "--trust-plugin"]],
        )

    def test__runner__nonzero_eval_exit__fails_for_every_exit_code(self) -> None:
        for exit_code in (1, 2, 130):
            with self.subTest(exit_code=exit_code):
                self.log_path.unlink(missing_ok=True)

                result = self.run_runner(
                    extra_env={"FAKE_CLAUDE_EVAL_EXIT": str(exit_code)}
                )

                self.assertNotEqual(result.returncode, 0)
                self.assertIn(f"code {exit_code}", result.stderr)
                self.assertEqual(list(self.results_root.glob("*")), [])

    def test__runner__positional_argument__fails_before_claude(self) -> None:
        result = self.run_runner("unexpected")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not accept arguments", result.stderr)
        self.assertEqual(self.calls(), [])


def main() -> None:
    unittest.main()
