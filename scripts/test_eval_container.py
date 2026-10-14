import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import eval_container as container


PROOF = {
    "ok": True,
    "privilege_mode": "strict",
    "checks": {
        "shell_dispatch": True,
        "helper_seccomp": 2,
        "bubblewrap": True,
        "combined_seccomp": 2,
    },
}


class ContainerRunnerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        settings = self.root / container.SETTINGS_PATH
        settings.parent.mkdir(parents=True)
        settings.write_text(json.dumps({"sandbox": {
            "enabled": True,
            "enableWeakerNestedSandbox": True,
            "bwrapPath": "/usr/bin/bwrap",
        }}))
        self.environment = {
            "ANTHROPIC_AUTH_TOKEN": "must-not-be-in-arguments-or-proof",
            "ANTHROPIC_BASE_URL": "https://gateway.invalid/anthropic",
        }

    def output(self, text, code=0):
        return subprocess.CompletedProcess([], code, stdout=text, stderr="")

    def run_suite(self, responses):
        with patch.dict(os.environ, self.environment, clear=True):
            with patch.object(container.subprocess, "run", side_effect=responses) as run:
                with patch("sys.stderr", io.StringIO()) as stderr:
                    code = container.run_in_container(
                        self.root, "native-image", "plugins/planner/evals/run.py"
                    )
        return code, run.call_args_list, stderr.getvalue()

    def test__valid_native_environment__preflight_precedes_suite(self):
        code, calls, error = self.run_suite([
            self.output("aarch64\n"), self.output("arm64 sha256:example\n"),
            self.output(json.dumps(PROOF)), self.output("", 0), self.output("removed"),
        ])
        self.assertEqual(code, 0, error)
        self.assertEqual(len(calls), 5)
        smoke = calls[2].args[0]
        suite = calls[3].args[0]
        self.assertIn("none", smoke)
        self.assertNotIn("ANTHROPIC_AUTH_TOKEN", smoke)
        self.assertIn("/usr/local/lib/claude-eval/preflight.py", smoke)
        self.assertIn("SHELL=/bin/bash", suite)
        self.assertIn("CLAUDE_CODE_SHELL=/bin/bash", suite)
        self.assertIn("MAX_COST_USD", suite)
        self.assertNotIn("--rm", suite)
        self.assertIn("CLAUDE_BIN=/usr/local/bin/claude-eval-keep", suite)
        self.assertTrue(any(arg.startswith("PLANNER_EVAL_RESULTS_ROOT=/workspace/plugins/planner/evals/results/environment-") for arg in suite))
        self.assertIn("sha256:example", smoke)
        self.assertIn("sha256:example", suite)
        self.assertNotIn("native-image", smoke)
        self.assertNotIn("native-image", suite)
        self.assertTrue(suite[-1].endswith("plugins/planner/evals/run.py"))
        serialized = json.dumps([call.args[0] for call in calls])
        self.assertNotIn(self.environment["ANTHROPIC_AUTH_TOKEN"], serialized)
        proofs = list(self.root.rglob("environment.json"))
        self.assertEqual(len(proofs), 1)
        self.assertNotIn(self.environment["ANTHROPIC_AUTH_TOKEN"], proofs[0].read_text())

    def test__privilege_selection__unknown_values_fail_before_docker(self):
        for value in ("true", "yes", "2", "", " 1"):
            with self.subTest(value=value):
                self.environment["CLAUDE_EVAL_INNER_SYS_ADMIN"] = value
                code, calls, error = self.run_suite([])
                self.assertNotEqual(code, 0)
                self.assertFalse(calls)
                self.assertIn("CLAUDE_EVAL_INNER_SYS_ADMIN", error)

    def test__opted_preflight__rejects_strict_proof(self):
        self.environment["CLAUDE_EVAL_INNER_SYS_ADMIN"] = "1"
        code, calls, error = self.run_suite([
            self.output("aarch64"), self.output("arm64 sha256:example"),
            self.output(json.dumps(PROOF)),
        ])
        self.assertNotEqual(code, 0)
        self.assertEqual(len(calls), 3)
        self.assertIn("privilege", error)

    def test__opted_environment__matching_proof_launches_and_records_mode(self):
        self.environment["CLAUDE_EVAL_INNER_SYS_ADMIN"] = "1"
        code, calls, error = self.run_suite([
            self.output("aarch64"), self.output("arm64 sha256:example"),
            self.output(json.dumps({**PROOF, "privilege_mode": "inner-sys-admin"})),
            self.output(""), self.output("removed"),
        ])
        self.assertEqual(code, 0, error)
        self.assertEqual(len(calls), 5)
        proof, = self.root.rglob("environment.json")
        self.assertEqual(json.loads(proof.read_text())["privilege_mode"], "inner-sys-admin")
        self.assertIn("CLAUDE_EVAL_INNER_SYS_ADMIN=1", calls[3].args[0])

    def test__opted_command__managed_settings_are_container_only(self):
        with patch.dict(os.environ, {"CLAUDE_EVAL_INNER_SYS_ADMIN": "1"}, clear=True):
            command = container.build_suite_command(self.root, "image", "plugins/planner/evals/run.py")
            smoke = container.build_preflight_command("image")
        self.assertIn("CLAUDE_EVAL_INNER_SYS_ADMIN=1", command)
        self.assertIn("CLAUDE_EVAL_INNER_SYS_ADMIN=1", smoke)
        self.assertIn("/etc/claude-code/managed-settings.json", command[-1])
        self.assertIn("/etc/claude-code/managed-settings.json", smoke[-1])
        self.assertIn("--tmpfs", smoke)
        self.assertIn("/etc/claude-code:rw,nosuid,nodev,noexec", smoke)
        self.assertIn(container.managed_settings_script(), smoke[-1])
        self.assertIn(container.managed_settings_script(), command[-1])
        self.assertIn("bwrap-cap-probe", command[-1])
        self.assertIn('"enableWeakerNestedSandbox": false', command[-1])
        self.assertNotIn(str(Path.home() / ".claude"), " ".join(command))
        self.assertNotIn("--security-opt", command)

    def aggregate(self, source):
        run = self.root / "run-current"
        run.mkdir()
        (run / "aggregate-result.json").write_text(json.dumps({
            "cases": [{"arms": {"with": [{"tracePath": source}]}}],
        }))

    def test__trace_capture__copies_only_cli_trace_and_scrubs_token_before_removal(self):
        source = "/tmp/claude-eval-native_1/out/trace.jsonl"
        self.aggregate(source)
        events = []

        def execute(command, **kwargs):
            events.append(command)
            if command[:2] == ["docker", "cp"]:
                Path(command[-1]).write_text(self.environment["ANTHROPIC_AUTH_TOKEN"] + "\\n")
            return self.output("", 0)

        with patch.dict(os.environ, self.environment, clear=True), \
             patch.object(container.subprocess, "run", side_effect=execute):
            self.assertEqual(container.run_paid_container(["docker", "run", "image"], self.root), 0)
        self.assertEqual([event[:2] for event in events], [["docker", "run"], ["docker", "cp"], ["docker", "rm"]])
        self.assertTrue(events[1][2].endswith(":" + source))
        trace, = self.root.glob("full-traces/*/trace.jsonl")
        self.assertEqual(trace.read_text(), "[REDACTED]\\n")

    def test__trace_capture__unsafe_or_missing_path_fails_closed(self):
        for source in (None, "/home/agent/.claude/.credentials.json",
                       "/tmp/claude-eval-native/out/../.credentials.json"):
            with self.subTest(source=source):
                run = self.root / "run-current"
                if run.exists():
                    (run / "aggregate-result.json").unlink()
                    run.rmdir()
                self.aggregate(source)
                with patch.object(container.subprocess, "run") as execute:
                    with self.assertRaises(container.ContainerError):
                        container.copy_traces("container-name", self.root)
                execute.assert_not_called()

    def test__trace_capture__symlink_is_rejected_without_reading_host_file(self):
        self.aggregate("/tmp/claude-eval-native/out/trace.jsonl")
        secret_file = self.root / "private-host-file"
        secret_file.write_text("must-not-read")

        def execute(command, **kwargs):
            Path(command[-1]).symlink_to(secret_file)
            return self.output("")

        with patch.object(container.subprocess, "run", side_effect=execute):
            with self.assertRaisesRegex(container.ContainerError, "symlink"):
                container.copy_traces("container-name", self.root)
        self.assertEqual(secret_file.read_text(), "must-not-read")
        self.assertFalse(list(self.root.glob("full-traces/*/trace.jsonl")))

    def test__trace_capture_failure__removes_container_and_blocks_success(self):
        self.aggregate("/tmp/claude-eval-native/out/trace.jsonl")
        with patch.object(container.subprocess, "run", side_effect=[self.output(""), self.output("", 1), self.output("removed")]) as execute:
            with self.assertRaisesRegex(container.ContainerError, "launch evidence incomplete"):
                container.run_paid_container(["docker", "run", "image"], self.root)
        self.assertEqual(len(execute.call_args_list), 3)
        self.assertEqual(execute.call_args_list[-1].args[0][:3], ["docker", "rm", "-f"])

    def test__preflight_failure__does_not_launch_suite(self):
        failures = (
            self.output("", 1),
            self.output(json.dumps({**PROOF, "ok": False})),
            self.output(json.dumps({**PROOF, "checks": {**PROOF["checks"], "combined_seccomp": 0}})),
            self.output("not JSON"),
        )
        for failure in failures:
            with self.subTest(failure=repr(failure)):
                code, calls, error = self.run_suite([
                    self.output("aarch64"), self.output("arm64 sha256:example"), failure,
                ])
                self.assertNotEqual(code, 0)
                self.assertEqual(len(calls), 3)
                self.assertTrue(error)

    def test__preflight_timeout__removes_its_container_without_launching_suite(self):
        code, calls, error = self.run_suite([
            self.output("aarch64"), self.output("arm64 sha256:example"),
            subprocess.TimeoutExpired("docker", 90), self.output("removed"),
        ])
        self.assertNotEqual(code, 0)
        self.assertIn("timed out", error)
        self.assertEqual(len(calls), 4)
        smoke = calls[2].args[0]
        name = smoke[smoke.index("--name") + 1]
        self.assertEqual(calls[3].args[0], ["docker", "rm", "-f", name])

    def test__architecture_mismatch_or_missing_image__does_not_launch_container(self):
        for image in (self.output("amd64 sha256:example"), self.output("", 1)):
            with self.subTest(image=image.stdout):
                code, calls, error = self.run_suite([self.output("aarch64"), image])
                self.assertNotEqual(code, 0)
                self.assertEqual(len(calls), 2)
                self.assertTrue(error)

    def test__missing_credentials__refuses_before_docker(self):
        self.environment = {}
        code, calls, error = self.run_suite([])
        self.assertEqual(code, 2)
        self.assertFalse(calls)
        self.assertIn("ANTHROPIC_AUTH_TOKEN", error)

    def test__missing_or_unsafe_settings__refuses_before_docker(self):
        settings = self.root / container.SETTINGS_PATH
        for body in (None, {"sandbox": {"enabled": False}},
                     {"sandbox": {"enabled": True, "bwrapPath": "/usr/local/bin/bwrap-noseccomp"}}):
            with self.subTest(body=body):
                if body is None:
                    settings.unlink(missing_ok=True)
                else:
                    settings.write_text(json.dumps(body))
                code, calls, error = self.run_suite([])
                self.assertNotEqual(code, 0)
                self.assertFalse(calls)
                self.assertTrue(error)

    def test__interrupted_suite__removes_model_container(self):
        code, calls, error = self.run_suite([
            self.output("aarch64"), self.output("arm64 sha256:example"),
            self.output(json.dumps(PROOF)), KeyboardInterrupt(), self.output("removed"),
        ])
        self.assertEqual(code, 130, error)
        self.assertEqual(len(calls), 5)
        command = calls[3].args[0]
        name = command[command.index("--name") + 1]
        self.assertEqual(calls[4].args[0], ["docker", "rm", "-f", name])

    def test__paid_runner_failure__is_returned_without_retry(self):
        code, calls, error = self.run_suite([
            self.output("aarch64"), self.output("arm64 sha256:example"),
            self.output(json.dumps(PROOF)), self.output("", 2), self.output("removed"),
        ])
        self.assertEqual(code, 2, error)
        self.assertEqual(len(calls), 5)


if __name__ == "__main__":
    unittest.main()
