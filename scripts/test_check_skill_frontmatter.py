#!/usr/bin/env python3
"""Договор стража заголовков навыков."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_skill_frontmatter as guard  # noqa: E402

VALID_HEADER = """---
name: demo-skill
description: Demo skill used by the guard contract test.
metadata:
  version: "1.2.3"
---

Тело навыка.
"""


class SkillFrontmatterGuardTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.skill_dir = self.root / "plugins" / "demo" / "skills" / "demo-skill"
        self.skill_dir.mkdir(parents=True)

    def write(self, text: str, name: str = "demo-skill") -> Path:
        skill_dir = self.root / "plugins" / "demo" / "skills" / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        path = skill_dir / "SKILL.md"
        path.write_text(text, encoding="utf-8")
        return path

    def test__version_in_metadata__passes(self):
        self.write(VALID_HEADER)

        self.assertEqual(guard.check_skill_frontmatter(self.root), [])

    def test__top_level_version__is_reported_with_metadata_hint(self):
        self.write(VALID_HEADER.replace('metadata:\n  version: "1.2.3"', 'version: "1.2.3"'))

        problems = guard.check_skill_frontmatter(self.root)

        self.assertEqual(len(problems), 1)
        self.assertIn("«version»", problems[0])
        self.assertIn("metadata.version", problems[0])

    def test__unknown_top_level_field__is_reported(self):
        self.write(VALID_HEADER.replace("metadata:", "owner: someone\nmetadata:"))

        problems = guard.check_skill_frontmatter(self.root)

        self.assertEqual(len(problems), 1)
        self.assertIn("«owner»", problems[0])

    def test__unquoted_metadata_version__is_reported_as_non_string(self):
        self.write(VALID_HEADER.replace('"1.2.3"', "1.2"))

        problems = guard.check_skill_frontmatter(self.root)

        self.assertEqual(len(problems), 1)
        self.assertIn("metadata.version", problems[0])

    def test__metadata_as_scalar__is_reported(self):
        self.write(VALID_HEADER.replace('metadata:\n  version: "1.2.3"', "metadata: 1.2.3"))

        problems = guard.check_skill_frontmatter(self.root)

        self.assertEqual(len(problems), 1)
        self.assertIn("metadata", problems[0])

    def test__name_differs_from_directory__is_reported(self):
        self.write(VALID_HEADER.replace("name: demo-skill", "name: other-skill"))

        problems = guard.check_skill_frontmatter(self.root)

        self.assertEqual(len(problems), 1)
        self.assertIn("каталог навыка", problems[0])

    def test__empty_description__is_reported(self):
        self.write(VALID_HEADER.replace("description: Demo skill used by the guard contract test.", 'description: ""'))

        problems = guard.check_skill_frontmatter(self.root)

        self.assertEqual(len(problems), 1)
        self.assertIn("description", problems[0])

    def test__missing_frontmatter__is_reported(self):
        self.write("# Навык без заголовка\n")

        problems = guard.check_skill_frontmatter(self.root)

        self.assertEqual(len(problems), 1)
        self.assertIn("рамка заголовка", problems[0])

    def test__unclosed_frontmatter__is_reported(self):
        self.write("---\nname: demo-skill\ndescription: Без закрывающего разделителя.\n")

        problems = guard.check_skill_frontmatter(self.root)

        self.assertEqual(len(problems), 1)
        self.assertIn("не закрыта", problems[0])

    def test__broken_yaml__is_reported_without_raising(self):
        self.write("---\nname: demo-skill\ndescription: [нераскрытый список\n---\n")

        problems = guard.check_skill_frontmatter(self.root)

        self.assertEqual(len(problems), 1)
        self.assertIn("YAML", problems[0])

    def test__every_shipped_skill__satisfies_the_specification(self):
        repository_root = Path(__file__).resolve().parent.parent

        self.assertEqual(guard.check_skill_frontmatter(repository_root), [])

    def test__missing_plugins_directory__is_usage_error(self):
        with self.assertRaises(SystemExit) as raised:
            guard.main(["--root", str(self.root / "нет-такого-каталога")])

        self.assertEqual(raised.exception.code, guard.EXIT_USAGE)


if __name__ == "__main__":
    unittest.main()
