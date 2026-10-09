"""Offline preflight contracts; subprocess fixtures do not prove Linux runtime support."""
import contextlib
import importlib.util
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("preflight", Path(__file__).with_name("preflight.py"))
preflight = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preflight)
WRAPPER_SPEC = importlib.util.spec_from_file_location("cap_wrapper", Path(__file__).with_name("bwrap-cap-probe.py"))
wrapper = importlib.util.module_from_spec(WRAPPER_SPEC)
WRAPPER_SPEC.loader.exec_module(wrapper)


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.binary = Path(self.tmp.name) / "claude"
        header = bytearray(64)
        header[:6] = b"\x7fELF\x02\x01"
        header[18:20] = (62).to_bytes(2, "little")
        self.binary.write_bytes(header)
        self.responses = {
            "shell_dispatch": (0, "apply-seccomp\n", ""),
            "helper_seccomp": (0, "CLAUDE_EVAL_PREFLIGHT\nSeccomp:\t2\n", ""),
            "bubblewrap": (0, "CLAUDE_EVAL_PREFLIGHT\n", ""),
            "combined_seccomp": (0, "CLAUDE_EVAL_PREFLIGHT\nSeccomp:\t2\n", ""),
        }
        self.calls = []
        self.settings = Path(self.tmp.name) / "managed-settings.json"
        self.settings_patch = patch.object(wrapper, "SETTINGS", self.settings, create=True)
        self.settings_patch.start()
        self.addCleanup(self.settings_patch.stop)

    def authorize(self):
        self.settings.write_text(json.dumps({"sandbox": {
            "enabled": True, "enableWeakerNestedSandbox": False,
            "bwrapPath": "/usr/local/bin/bwrap-cap-probe",
        }}))

    def run_command(self, command, **kwargs):
        self.calls.append((command, kwargs))
        self.assertNotIn("ANTHROPIC_AUTH_TOKEN", kwargs["env"])
        self.assertEqual(kwargs["env"]["SHELL"], "/bin/bash")
        if "--version" in command or "-V" in command:
            name = Path(command[0]).name
            outputs = {"claude": "2.1.286 (Claude Code)", "git": "git version 2.39.5",
                       "bwrap": "bubblewrap 0.8.0", "node": "v22.0.0", "socat": "socat version 1.7.4.4",
                       "bash": "GNU bash, version 5.2.15", "python3": "Python 3.11.2"}
            return subprocess.CompletedProcess(command, 0, outputs[name] + "\n", "")
        stage = command[-1]
        self.assertIn(stage, self.responses)
        if stage in ("helper_seccomp", "combined_seccomp"):
            fd, = kwargs["pass_fds"]
            self.assertEqual(os.fstat(fd).st_ino, self.binary.stat().st_ino)
            self.assertIn("/proc/self/fd/3", command[4])
        if stage == "combined_seccomp":
            self.assertNotIn("--preserve-fds", command[4])
            self.assertIn("--cap-drop ALL", command[4])
            self.assertIn("--cap-add CAP_SETFCAP", command[4])
            self.assertNotIn("--cap-add CAP_SYS_ADMIN", command[4])
            if os.environ.get("CLAUDE_EVAL_INNER_SYS_ADMIN") == "1":
                self.assertIn("/usr/local/bin/bwrap-cap-probe ", command[4])
            else:
                self.assertIn("/usr/bin/bwrap ", command[4])
        code, out, err = self.responses[stage]
        return subprocess.CompletedProcess(command, code, out, err)

    def invoke(self):
        out, err = io.StringIO(), io.StringIO()
        with patch.object(preflight, "CLAUDE", str(self.binary)), \
             patch.object(preflight.platform, "system", return_value="Linux"), \
             patch.object(preflight.platform, "machine", return_value="x86_64"), \
             patch.object(preflight.subprocess, "run", side_effect=self.run_command), \
             patch.object(preflight.runpy, "run_path", return_value={"privilege_mode": wrapper.privilege_mode}), \
             patch.dict(os.environ, {"ANTHROPIC_AUTH_TOKEN": "must-not-leak"}), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = preflight.main()
        return code, out.getvalue(), err.getvalue()

    def test__full_preflight__valid_evidence__safe_json(self):
        code, out, err = self.invoke()
        self.assertEqual((code, err), (0, ""))
        result = json.loads(out)
        self.assertTrue(result["ok"])
        self.assertEqual(result["checks"], {"shell_dispatch": True, "helper_seccomp": 2,
                                          "bubblewrap": True, "combined_seccomp": 2})
        self.assertEqual(result["arch"], "amd64")
        self.assertNotIn("must-not-leak", out)
        self.assertEqual([command[-1] for command, _ in self.calls if command[0] == "/bin/bash" and "--version" not in command],
                         list(self.responses))

    def test__opted_budget__proof_names_mode_and_keeps_seccomp(self):
        self.authorize()
        with patch.dict(os.environ, {"CLAUDE_EVAL_INNER_SYS_ADMIN": "1"}):
            code, out, err = self.invoke()
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(json.loads(out)["privilege_mode"], "inner-sys-admin")
        self.assertEqual(json.loads(out)["checks"]["combined_seccomp"], 2)

    def test__preflight__selected_mode_requires_matching_protected_config(self):
        for selected, authorize in (("1", False), ("0", True)):
            with self.subTest(selected=selected):
                if authorize:
                    self.authorize()
                with patch.dict(os.environ, {"CLAUDE_EVAL_INNER_SYS_ADMIN": selected}):
                    code, out, err = self.invoke()
                self.assertNotEqual(code, 0)
                self.assertEqual(out, "")
                self.assertIn("authorization", err)
                self.assertFalse(self.calls)

    def test__unknown_privilege__refuses_without_subprocess(self):
        with patch.dict(os.environ, {"CLAUDE_EVAL_INNER_SYS_ADMIN": "yes"}):
            code, out, err = self.invoke()
        self.assertNotEqual(code, 0)
        self.assertFalse(self.calls)
        self.assertIn("CLAUDE_EVAL_INNER_SYS_ADMIN", err)

    def test__probe__bad_evidence__refuses(self):
        cases = [
            ("shell_dispatch", (0, "\n", "")),
            ("helper_seccomp", (1, "", "prctl: Invalid argument")),
            ("helper_seccomp", (0, "CLAUDE_EVAL_PREFLIGHT\nSeccomp:\t0\n", "")),
            ("bubblewrap", (0, "", "")),
            ("bubblewrap", (1, "CLAUDE_EVAL_PREFLIGHT\n", "bwrap failed")),
            ("combined_seccomp", (0, "Seccomp:\t2\n", "")),
            ("combined_seccomp", (0, "CLAUDE_EVAL_PREFLIGHT\nSeccomp:\t0\n", "")),
            ("combined_seccomp", (0, "CLAUDE_EVAL_PREFLIGHT\nSeccomp:\t2\nSeccomp:\t0\n", "")),
        ]
        for stage, response in cases:
            with self.subTest(stage=stage, response=response):
                original = self.responses[stage]
                self.responses[stage] = response
                code, out, err = self.invoke()
                self.responses[stage] = original
                self.assertNotEqual(code, 0)
                self.assertEqual(out, "")
                self.assertIn(stage, err)

    def test__elf__wrong_arch_or_not_native__refuses(self):
        for data in (b"#!/bin/sh\n", b"\x7fELF\x02\x01" + b"\0" * 12 + (183).to_bytes(2, "little")):
            with self.subTest(data=data):
                self.binary.write_bytes(data)
                code, out, err = self.invoke()
                self.assertNotEqual(code, 0)
                self.assertEqual(out, "")
                self.assertIn("ELF", err)

    def test__wrapper__protected_config_survives_empty_child_environment(self):
        self.authorize()
        arguments = ["--unshare-all", "--cap-drop", "ALL", "--cap-add", "CAP_SETFCAP", "--", "echo", "ok"]
        with patch.dict(os.environ, {}, clear=True), patch.object(wrapper.os, "execv") as execute:
            wrapper.main(arguments)
        command = execute.call_args.args[1]
        self.assertIn("CAP_SYS_ADMIN", command)
        self.assertEqual(command[-3:], ["--", "echo", "ok"])

    def test__wrapper__environment_alone_does_not_authorize_capability(self):
        arguments = ["--unshare-all", "--cap-drop", "ALL", "--", "echo", "ok"]
        with patch.dict(os.environ, {"CLAUDE_EVAL_INNER_SYS_ADMIN": "1"}, clear=True), \
             patch.object(wrapper.os, "execv") as execute:
            wrapper.main(arguments)
        self.assertNotIn("CAP_SYS_ADMIN", execute.call_args.args[1])

    def test__wrapper__malformed_or_wrong_authorization_fails_closed(self):
        for data in ("not JSON", json.dumps({"sandbox": {"enabled": False}}),
                     json.dumps({"sandbox": {"enabled": True, "enableWeakerNestedSandbox": True,
                                              "bwrapPath": "/usr/local/bin/bwrap-cap-probe"}})):
            with self.subTest(data=data):
                self.settings.write_text(data)
                with patch.dict(os.environ, {}, clear=True), patch.object(wrapper.os, "execv") as execute:
                    with self.assertRaisesRegex(SystemExit, "authorization"):
                        wrapper.main(["--unshare-all", "--cap-drop", "ALL", "--", "echo", "ok"])
                execute.assert_not_called()

    def test__wrapper__namespace_required_for_privileged_inner_command(self):
        self.authorize()
        with patch.dict(os.environ, {"CLAUDE_EVAL_INNER_SYS_ADMIN": "1"}, clear=True), \
             patch.object(wrapper.os, "execv") as execute:
            with self.assertRaisesRegex(SystemExit, "isolated user namespace"):
                wrapper.main(["--cap-drop", "ALL", "--", "echo", "ok"])
        execute.assert_not_called()

    def test__keep_wrapper__only_plugin_eval_gets_one_keep_temp(self):
        # Реально исполняем shell-ветвление с безопасной заменой конечного CLI.
        source = Path(__file__).with_name("keep-cli.sh").read_text()
        native = Path(self.tmp.name) / "native"
        native.write_text('#!/bin/bash\nprintf \'%s\\n\' "$@"\n')
        native.chmod(0o755)
        script = source.replace("/usr/local/share/npm-global/bin/claude", str(native))
        shell = Path(self.tmp.name) / "keep-cli.sh"
        shell.write_text(script)
        for arguments, expected in [
            (["--version"], ["--version"]),
            (["plugin", "eval", "/cases"], ["plugin", "eval", "/cases", "--keep-temp"]),
            (["plugin", "eval", "--keep-temp"], ["plugin", "eval", "--keep-temp"]),
        ]:
            with self.subTest(arguments=arguments):
                output = subprocess.check_output(["/bin/bash", str(shell), *arguments], text=True)
                self.assertEqual(output.splitlines(), expected)

    def test__bash__real_process__preserves_argv0(self):
        result = subprocess.run(["/bin/bash", "--noprofile", "--norc", "-c",
                                 "exec python3 -c 'import os; print(os.environ.get(\"ARGV0\"))'"],
                                env={"PATH": os.environ["PATH"], "ARGV0": "apply-seccomp"},
                                capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout, "apply-seccomp\n")


if __name__ == "__main__":
    unittest.main()
