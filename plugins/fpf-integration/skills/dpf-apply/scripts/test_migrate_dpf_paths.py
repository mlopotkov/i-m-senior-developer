#!/usr/bin/env python3
"""Договор команды переноса сводов на канонические имена путей.

Все случаи работают во временных каталогах: команда пишет в домашний каталог и
в проект, поэтому её нельзя проверять на живых данных.
"""

from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

import migrate_dpf_paths as migrate  # noqa: E402

DPF_BODY = """---
dpf_id: {pkg_id}
kind: Domain Principle Framework
status: active
review_due: 2099-01-01
owner: guardian
---

> conformance: E.4.DPF.DA: admissibleForDeclaredDPFUse
"""


class MigrationTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.home = self.root / "home"
        self.project = self.root / "project"
        self.home_claude = self.home / ".claude"
        self.project_claude = self.project / ".claude"
        self.home_claude.mkdir(parents=True)
        self.project_claude.mkdir(parents=True)

    def make_package(self, root: Path, pkg_id: str) -> Path:
        package = root / pkg_id
        package.mkdir(parents=True, exist_ok=True)
        (package / "DPF.md").write_text(DPF_BODY.format(pkg_id=pkg_id), encoding="utf-8")
        return package

    def run_migration(self, *args: str) -> tuple[int, str]:
        output = io.StringIO()
        argv = ["--home", str(self.home), "--project", str(self.project), *args]
        with mock.patch.object(sys, "stdout", output):
            code = migrate.main(argv)
        return code, output.getvalue()

    def tree(self) -> set[str]:
        paths = set()
        for base in (self.home, self.project):
            for path in base.rglob("*"):
                paths.add(str(path.relative_to(self.root)))
        return paths


class PreviewTests(MigrationTestCase):
    def test__preview__changes_nothing_on_disk(self):
        self.make_package(self.project_claude / "frameworks", "DPF-ONE")
        before = self.tree()

        code, report = self.run_migration()

        self.assertEqual(code, 0)
        self.assertIn(str(self.project_claude / "frameworks"), report)
        self.assertIn(str(self.project_claude / ".dpf"), report)
        self.assertIn("--apply", report)
        self.assertEqual(self.tree(), before)

    def test__nothing_to_migrate__reports_empty_plan(self):
        self.make_package(self.project_claude / ".dpf", "DPF-ONE")

        code, report = self.run_migration()

        self.assertEqual(code, 0)
        self.assertIn("переносить нечего", report)


class ApplyTests(MigrationTestCase):
    def test__apply__moves_project_and_home_roots(self):
        self.make_package(self.project_claude / "frameworks", "DPF-PROJECT")
        self.make_package(self.home_claude / "frameworks", "DPF-USER")

        code, _ = self.run_migration("--apply")

        self.assertEqual(code, 0)
        self.assertTrue((self.project_claude / ".dpf" / "DPF-PROJECT" / "DPF.md").is_file())
        self.assertTrue((self.home_claude / ".dpf" / "DPF-USER" / "DPF.md").is_file())
        self.assertFalse((self.project_claude / "frameworks").exists())
        self.assertFalse((self.home_claude / "frameworks").exists())

    def test__apply__renames_configuration_files(self):
        (self.project_claude / "frameworks.paths").write_text("dpf\n", encoding="utf-8")
        (self.project_claude / "frameworks.trusted").write_text("DPF-DRAFT\n", encoding="utf-8")
        (self.home_claude / "frameworks.paths").write_text("/abs/other\n", encoding="utf-8")

        self.run_migration("--apply")

        self.assertEqual((self.project_claude / ".dpf.paths").read_text(encoding="utf-8"), "dpf\n")
        self.assertEqual(
            (self.project_claude / ".dpf.trusted").read_text(encoding="utf-8"), "DPF-DRAFT\n"
        )
        self.assertEqual((self.home_claude / ".dpf.paths").read_text(encoding="utf-8"), "/abs/other\n")
        self.assertFalse((self.project_claude / "frameworks.paths").exists())

    def test__apply__rewrites_only_entries_pointing_at_migrated_roots(self):
        self.make_package(self.project_claude / "frameworks", "DPF-ONE")
        (self.home_claude / "frameworks.paths").write_text(
            f"{self.project_claude / 'frameworks'}\n{self.root / 'elsewhere'}\n", encoding="utf-8"
        )

        self.run_migration("--apply")

        lines = (self.home_claude / ".dpf.paths").read_text(encoding="utf-8").splitlines()
        self.assertEqual(
            lines, [str(self.project_claude / ".dpf"), str(self.root / "elsewhere")]
        )

    def test__apply__moves_owned_bank_links_of_both_owner_layouts(self):
        for owners_dirname in (".banks", ".fpf_banks"):
            with self.subTest(owners_dirname=owners_dirname):
                self.setUp()
                bank = self.root / "bank" / ".dpf"
                package = self.make_package(bank, "DPF-BANK")
                legacy_links = self.home_claude / "frameworks.d"
                owner = legacy_links / owners_dirname / "fpf-competency-bank"
                owner.mkdir(parents=True)
                os.symlink(package, owner / "DPF-BANK")
                os.symlink(
                    os.path.join(owners_dirname, "fpf-competency-bank", "DPF-BANK"),
                    legacy_links / "DPF-BANK",
                )

                code, _ = self.run_migration("--apply")

                self.assertEqual(code, 0)
                new_links = self.home_claude / "dpf.d"
                self.assertEqual(
                    os.path.realpath(new_links / "DPF-BANK"), os.path.realpath(package)
                )
                self.assertEqual(
                    os.readlink(new_links / "DPF-BANK"),
                    os.path.join(".fpf_banks", "fpf-competency-bank", "DPF-BANK"),
                )

    def test__apply__is_idempotent(self):
        self.make_package(self.project_claude / "frameworks", "DPF-ONE")
        self.run_migration("--apply")
        after_first = self.tree()

        code, report = self.run_migration("--apply")

        self.assertEqual(code, 0)
        self.assertIn("переносить нечего", report)
        self.assertEqual(self.tree(), after_first)


class RefusalTests(MigrationTestCase):
    def test__occupied_destination__refuses_without_touching_anything(self):
        self.make_package(self.project_claude / "frameworks", "DPF-ONE")
        self.make_package(self.project_claude / ".dpf", "DPF-OTHER")
        before = self.tree()

        code, report = self.run_migration("--apply")

        self.assertEqual(code, migrate.EXIT_REFUSED)
        self.assertIn("уже существует", report)
        self.assertEqual(self.tree(), before)

    def test__existing_canonical_config__is_not_overwritten(self):
        (self.project_claude / "frameworks.trusted").write_text("DPF-OLD\n", encoding="utf-8")
        (self.project_claude / ".dpf.trusted").write_text("DPF-NEW\n", encoding="utf-8")

        code, report = self.run_migration("--apply")

        self.assertEqual(code, migrate.EXIT_REFUSED)
        self.assertEqual(
            (self.project_claude / ".dpf.trusted").read_text(encoding="utf-8"), "DPF-NEW\n"
        )
        self.assertIn("уже существует", report)

    def test__foreign_bank_link__is_reported_and_left_in_place(self):
        bank = self.root / "other-bank" / "frameworks"
        package = self.make_package(bank, "DPF-FOREIGN")
        legacy_links = self.home_claude / "frameworks.d"
        legacy_links.mkdir(parents=True)
        os.symlink(package, legacy_links / "DPF-FOREIGN")

        code, report = self.run_migration("--apply")

        self.assertEqual(code, migrate.EXIT_REFUSED)
        self.assertIn("DPF-FOREIGN", report)
        self.assertIn("не принадлежит известному банку", report)
        self.assertTrue((legacy_links / "DPF-FOREIGN").is_symlink())
        self.assertFalse((self.home_claude / "dpf.d" / "DPF-FOREIGN").exists())

    def test__legacy_published_file__is_only_reported(self):
        (self.home_claude / "frameworks.published").write_text("/some/bank/frameworks\n", encoding="utf-8")

        code, report = self.run_migration("--apply")

        self.assertEqual(code, 0)
        self.assertIn("frameworks.published", report)
        self.assertTrue((self.home_claude / "frameworks.published").is_file())


if __name__ == "__main__":
    unittest.main()
