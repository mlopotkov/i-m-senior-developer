import os
from pathlib import Path
import unittest
from unittest.mock import patch

import run_in_docker as runner


class PlannerContainerTests(unittest.TestCase):
    def test__command__uses_planner_and_explicit_bash(self):
        command = runner.build_docker_command(Path("/repo"), "native-image")
        self.assertIn("SHELL=/bin/bash", command)
        self.assertIn("CLAUDE_CODE_SHELL=/bin/bash", command)
        self.assertNotIn("--platform", command)
        self.assertEqual(command[-4:], [
            "native-image", "/bin/bash", "-c",
            "chmod o+x /home/agent && exec /usr/bin/python3 plugins/planner/evals/run.py",
        ])

    def test__main__image_override__passes_through_shared_gate(self):
        with patch.dict(os.environ, {"PLANNER_EVAL_IMAGE": "custom-native"}):
            with patch.object(runner, "run_in_container", return_value=2) as gate:
                self.assertEqual(runner.main(), 2)
        gate.assert_called_once_with(runner.REPO_ROOT, "custom-native", "plugins/planner/evals/run.py")


if __name__ == "__main__":
    unittest.main()
