from pathlib import Path
import unittest

import yaml


class AgentSkillDeliveryTests(unittest.TestCase):
    def test__registered_roles__preload_their_own_method(self):
        root = Path(__file__).resolve().parents[1]
        for name in ("architect", "code-implementer", "code-reviewer"):
            with self.subTest(role=name):
                fields = yaml.safe_load((root / "agents" / f"{name}.md").read_text().split("---", 2)[1])
                self.assertEqual(fields.get("skills"), [f"sdlc:{name}"])
                self.assertIn("Skill", fields["tools"])


if __name__ == "__main__":
    unittest.main()
