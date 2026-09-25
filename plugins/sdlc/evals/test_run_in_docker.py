import os
from pathlib import Path
import unittest
from unittest.mock import patch

from run_in_docker import (
    GATEWAY_VARIABLES,
    SYSTEM_PATH,
    build_docker_command,
)


class SdlcDockerEvalRunnerTest(unittest.TestCase):
    def test__build_docker_command__default_environment__uses_sandbox_safe_paths(self) -> None:
        repo_root = Path("/repo")
        settings_path = repo_root / "plugins/sdlc/evals/container-settings.json"
        secret = "must-not-appear-in-command"

        with patch.dict(os.environ, {"ANTHROPIC_AUTH_TOKEN": secret}):
            command = build_docker_command(repo_root, "ccd-eval-py:latest")

        self.assertIn(f"PATH={SYSTEM_PATH}", command)
        self.assertNotIn("pyenv", " ".join(command))
        self.assertNotIn("--platform", command)
        self.assertIn(
            f"{settings_path}:/home/agent/.claude/settings.json:ro",
            command,
        )
        self.assertEqual(
            command[-4:],
            [
                "ccd-eval-py:latest",
                "/bin/bash",
                "-c",
                "chmod o+x /home/agent && "
                "exec /usr/bin/python3 plugins/sdlc/evals/run.py",
            ],
        )
        for variable in GATEWAY_VARIABLES:
            self.assertIn(variable, command)
        self.assertNotIn(secret, command)


if __name__ == "__main__":
    unittest.main()
