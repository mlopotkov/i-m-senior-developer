#!/usr/bin/env python3
"""Договор SessionStart-публикатора сводов банка."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HOOKS_DIR = Path(__file__).parent
sys.path.insert(0, str(HOOKS_DIR))

import publish_dpf_bank_links as publisher  # noqa: E402

RESOLVE_SCRIPT = (
    HOOKS_DIR.parent.parent
    / "fpf-integration"
    / "skills"
    / "dpf-apply"
    / "scripts"
    / "resolve.py"
)

DPF_BODY = """---
dpf_id: {pkg_id}
kind: Domain Principle Framework
status: active
review_due: 2099-01-01
owner: guardian
---

# Тело свода

> conformance: CC-DPF.1–9 verified; E.4.DPF.DA: admissibleForDeclaredDPFUse (critic, guardian, 2026-07-13)
"""


class PublisherTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.home = self.root / "home"
        self.claude_dir = self.home / ".claude"
        self.claude_dir.mkdir(parents=True)
        self.links_dir = self.claude_dir / publisher.LINKS_DIRNAME

    def make_bank(self, name: str, package_ids: list[str], *, competency_map: bool = False) -> Path:
        packages = self.root / name / publisher.PACKAGES_DIRNAME
        packages.mkdir(parents=True, exist_ok=True)
        for pkg_id in package_ids:
            package = packages / pkg_id
            package.mkdir(exist_ok=True)
            (package / "DPF.md").write_text(DPF_BODY.format(pkg_id=pkg_id), encoding="utf-8")
        if competency_map:
            (packages / "competency-map.md").write_text(
                "| id | cues |\n|---|---|\n| " + package_ids[0] + " | связность |\n",
                encoding="utf-8",
            )
        return packages.parent

    def run_publisher(self, plugin_root: Path) -> tuple[int, str]:
        stderr = io.StringIO()
        with mock.patch.dict(
            os.environ,
            {"HOME": str(self.home), "CLAUDE_PLUGIN_ROOT": str(plugin_root)},
        ):
            with mock.patch.object(sys, "stderr", stderr):
                code = publisher.main()
        return code, stderr.getvalue()

    def published_ids(self) -> set[str]:
        if not self.links_dir.is_dir():
            return set()
        return {
            entry.name
            for entry in self.links_dir.iterdir()
            if entry.name != publisher.OWNERS_DIRNAME
        }


class PublishFrameworksPathTests(PublisherTestCase):
    def test__session_start_hook__runs_publisher_command(self):
        payload = json.loads((HOOKS_DIR / "hooks.json").read_text(encoding="utf-8"))

        command = payload["hooks"]["SessionStart"][0]["hooks"][0]["command"]

        self.assertEqual(
            command,
            'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/publish_dpf_bank_links.py"',
        )

    def test__publisher__links_every_shipped_package(self):
        plugin_root = self.make_bank("bank-a", ["DPF-ONE", "LPF-TWO"])

        code, stderr = self.run_publisher(plugin_root)

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(self.published_ids(), {"DPF-ONE", "LPF-TWO"})
        self.assertEqual(os.readlink(self.links_dir / "DPF-ONE"), ".fpf_banks/fpf-competency-bank/DPF-ONE")
        self.assertTrue((self.links_dir / "DPF-ONE" / "DPF.md").is_file())

    def test__second_bank__keeps_packages_of_the_first(self):
        first = self.make_bank("bank-a", ["DPF-ONE"])
        second = self.make_bank("bank-b", ["DPF-OTHER"])
        other_owner = self.links_dir / publisher.OWNERS_DIRNAME / "other-bank"
        other_owner.mkdir(parents=True)
        os.symlink(second / publisher.PACKAGES_DIRNAME / "DPF-OTHER", other_owner / "DPF-OTHER")
        os.symlink(
            os.path.join(publisher.OWNERS_DIRNAME, "other-bank", "DPF-OTHER"),
            self.links_dir / "DPF-OTHER",
        )

        self.run_publisher(first)
        self.run_publisher(first)

        self.assertEqual(self.published_ids(), {"DPF-ONE", "DPF-OTHER"})
        self.assertTrue((self.links_dir / "DPF-OTHER" / "DPF.md").is_file())

    def test__foreign_entry_with_same_id__is_reported_and_kept(self):
        plugin_root = self.make_bank("bank-a", ["DPF-ONE"])
        foreign = self.make_bank("bank-b", ["DPF-ONE"])
        self.links_dir.mkdir(parents=True)
        os.symlink(foreign / publisher.PACKAGES_DIRNAME / "DPF-ONE", self.links_dir / "DPF-ONE")

        code, stderr = self.run_publisher(plugin_root)

        self.assertEqual(code, 0)
        self.assertIn("DPF-ONE", stderr)
        self.assertEqual(
            os.path.realpath(self.links_dir / "DPF-ONE"),
            os.path.realpath(foreign / publisher.PACKAGES_DIRNAME / "DPF-ONE"),
        )

    def test__version_upgrade__retargets_only_own_links(self):
        old_version = self.make_bank("bank-1.0", ["DPF-ONE"])
        self.run_publisher(old_version)
        new_version = self.make_bank("bank-1.1", ["DPF-ONE"])

        self.run_publisher(new_version)

        self.assertEqual(
            os.path.realpath(self.links_dir / "DPF-ONE"),
            os.path.realpath(new_version / publisher.PACKAGES_DIRNAME / "DPF-ONE"),
        )

    def test__package_dropped_from_shipment__loses_its_own_link(self):
        self.run_publisher(self.make_bank("bank-1.0", ["DPF-ONE", "LPF-TWO"]))

        self.run_publisher(self.make_bank("bank-1.1", ["DPF-ONE"]))

        self.assertEqual(self.published_ids(), {"DPF-ONE"})

    def test__missing_target_of_own_link__does_not_make_it_foreign(self):
        plugin_root = self.make_bank("bank-1.0", ["DPF-ONE"])
        self.run_publisher(plugin_root)
        for path in sorted((plugin_root / publisher.PACKAGES_DIRNAME / "DPF-ONE").iterdir()):
            path.unlink()
        (plugin_root / publisher.PACKAGES_DIRNAME / "DPF-ONE").rmdir()
        new_version = self.make_bank("bank-1.1", ["DPF-ONE"])

        code, stderr = self.run_publisher(new_version)

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertTrue((self.links_dir / "DPF-ONE" / "DPF.md").is_file())

    def test__competency_map__is_published_next_to_owned_links(self):
        plugin_root = self.make_bank("bank-a", ["DPF-ONE"], competency_map=True)

        self.run_publisher(plugin_root)

        owner_map = (
            self.links_dir / publisher.OWNERS_DIRNAME / publisher.BANK_NAME / "competency-map.md"
        )
        self.assertTrue(owner_map.is_file())
        self.assertNotIn("competency-map.md", self.published_ids())

    def test__published_file__is_no_longer_written(self):
        published_file = self.claude_dir / "frameworks.published"
        published_file.write_text("/legacy/bank/frameworks\n", encoding="utf-8")
        paths_file = self.claude_dir / "frameworks.paths"
        paths_file.write_text("/human/frameworks\n", encoding="utf-8")

        self.run_publisher(self.make_bank("bank-a", ["DPF-ONE"]))

        self.assertEqual(published_file.read_text(encoding="utf-8"), "/legacy/bank/frameworks\n")
        self.assertEqual(paths_file.read_text(encoding="utf-8"), "/human/frameworks\n")

    def test__legacy_links_directory__is_left_untouched(self):
        legacy_links = self.claude_dir / "frameworks.d"
        legacy_owner = legacy_links / ".banks" / publisher.BANK_NAME
        legacy_owner.mkdir(parents=True)
        legacy_target = self.root / "old-install" / "frameworks" / "DPF-ONE"
        legacy_target.mkdir(parents=True)
        os.symlink(legacy_target, legacy_owner / "DPF-ONE")
        os.symlink(
            os.path.join(".banks", publisher.BANK_NAME, "DPF-ONE"),
            legacy_links / "DPF-ONE",
        )

        self.run_publisher(self.make_bank("bank-a", ["DPF-ONE"]))

        self.assertEqual(
            os.readlink(legacy_links / "DPF-ONE"),
            os.path.join(".banks", publisher.BANK_NAME, "DPF-ONE"),
        )
        self.assertEqual(
            os.path.realpath(legacy_owner / "DPF-ONE"), os.path.realpath(legacy_target)
        )

    def test__empty_plugin_root__reports_reason_without_failing_session_start(self):
        stderr = io.StringIO()
        with mock.patch.dict(os.environ, {"HOME": str(self.home), "CLAUDE_PLUGIN_ROOT": ""}):
            with mock.patch.object(sys, "stderr", stderr):
                code = publisher.main()
        stderr = stderr.getvalue()

        self.assertEqual(code, 0)
        self.assertIn("CLAUDE_PLUGIN_ROOT", stderr)
        self.assertEqual(self.published_ids(), set())

    def test__bank_without_packages__reports_reason(self):
        empty = self.root / "bank-empty"
        (empty / publisher.PACKAGES_DIRNAME).mkdir(parents=True)

        code, stderr = self.run_publisher(empty)

        self.assertEqual(code, 0)
        self.assertIn("нет сводов", stderr)

    def test__write_error__reports_reason_without_failing_session_start(self):
        plugin_root = self.make_bank("bank-a", ["DPF-ONE"])

        with mock.patch.object(publisher.os, "symlink", side_effect=OSError("denied")):
            code, stderr = self.run_publisher(plugin_root)

        self.assertEqual(code, 0)
        self.assertIn("denied", stderr)


class ResolverSeesPublishedPackagesTests(PublisherTestCase):
    def resolve(self, project: Path, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(RESOLVE_SCRIPT), *args],
            cwd=project,
            env=dict(os.environ, HOME=str(self.home)),
            capture_output=True,
            text=True,
        )

    def test__resolver__finds_packages_of_two_banks_at_once(self):
        project = self.root / "project"
        project.mkdir()
        first = self.make_bank("bank-a", ["DPF-ONE"])
        second_owner = self.links_dir / publisher.OWNERS_DIRNAME / "other-bank"
        second = self.make_bank("bank-b", ["DPF-OTHER"])
        second_owner.mkdir(parents=True)
        os.symlink(second / publisher.PACKAGES_DIRNAME / "DPF-OTHER", second_owner / "DPF-OTHER")
        os.symlink(
            os.path.join(publisher.OWNERS_DIRNAME, "other-bank", "DPF-OTHER"),
            self.links_dir / "DPF-OTHER",
        )
        self.run_publisher(first)

        listed = self.resolve(project, "--list", "--json")

        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertEqual(
            {row["id"] for row in json.loads(listed.stdout)},
            {"DPF-ONE", "DPF-OTHER"},
        )
        for pkg_id in ("DPF-ONE", "DPF-OTHER"):
            found = self.resolve(project, pkg_id)
            self.assertEqual(found.returncode, 0, found.stdout + found.stderr)


if __name__ == "__main__":
    unittest.main()
