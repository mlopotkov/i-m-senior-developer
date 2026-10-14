#!/usr/bin/env python3
"""Тесты режима --verify резолвера. Запуск:
  python3 -m pytest test_resolve.py
  python3 test_resolve.py

Фикстуры — мини-пакеты DPF.md во временных каталогах, по одной причине
отказа на каждую проверку контракта (0..4) плюс переключение --scope.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import resolve  # noqa: E402

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resolve.py")

ADMISSIBLE = (
    "> conformance: CC-DPF.1–9 verified; "
    "E.4.DPF.DA: admissibleForDeclaredDPFUse (critic, guardian, 2026-07-13)"
)
REPAIR = (
    "> conformance: CC-DPF.1–9 verified; "
    "E.4.DPF.DA: repairBeforeDPFUse (critic, guardian, 2026-07-13)"
)


def make_pkg(
    root,
    pkg_id,
    *,
    dpf_id="__same__",
    kind="Domain Principle Framework",
    status="active",
    review_due="2099-01-01",
    owner="guardian",
    conformance=ADMISSIBLE,
    references=None,
    apply_prompt=None,
):
    if dpf_id == "__same__":
        dpf_id = pkg_id
    pkg_dir = os.path.join(root, pkg_id)
    os.makedirs(pkg_dir, exist_ok=True)
    fm_lines = ["---"]
    for key, val in (
        ("dpf_id", dpf_id),
        ("kind", kind),
        ("status", status),
        ("review_due", review_due),
        ("owner", owner),
        ("name", "человекочитаемое назначение"),
    ):
        if val is not None:
            fm_lines.append(f"{key}: {val}")
    fm_lines.append("---")
    body = ["", "# Тело пакета", ""]
    if conformance:
        body.append(conformance)
    with open(os.path.join(pkg_dir, "DPF.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(fm_lines + body) + "\n")
    if references is not None:
        ref_dir = os.path.join(pkg_dir, "references")
        os.makedirs(ref_dir, exist_ok=True)
        with open(os.path.join(ref_dir, "critic-review.md"), "w", encoding="utf-8") as fh:
            fh.write(references + "\n")
    if apply_prompt is not None:
        assets = os.path.join(pkg_dir, "assets")
        os.makedirs(assets, exist_ok=True)
        with open(os.path.join(assets, "apply-prompt.md"), "w", encoding="utf-8") as fh:
            fh.write(apply_prompt + "\n")
    return pkg_dir


def levels_for(root):
    return [("project", root)]


def check(result, name):
    for c in result["checks"]:
        if c["name"] == name:
            return c
    raise AssertionError(f"нет проверки {name!r} в {[c['name'] for c in result['checks']]}")


# --- проверка 0: резолюция ---

def test_not_found_exits_1():
    with tempfile.TemporaryDirectory() as root:
        result, code = resolve.run_verify("DPF-NOPE", "bank", levels_for(root))
        assert code == 1
        assert result["ok"] is False
        assert check(result, "resolve")["ok"] is False


# --- проверка 1: структура + поля ---

def test_valid_admissible_passes_bank():
    with tempfile.TemporaryDirectory() as root:
        make_pkg(root, "DPF-VALID")
        result, code = resolve.run_verify("DPF-VALID", "bank", levels_for(root))
        assert code == 0, result
        assert result["ok"] is True
        assert all(c["ok"] for c in result["checks"])


def test_missing_owner_fails_field_check_both_scopes():
    with tempfile.TemporaryDirectory() as root:
        make_pkg(root, "DPF-NOOWNER", owner=None)
        for scope in ("local", "bank"):
            result, code = resolve.run_verify("DPF-NOOWNER", scope, levels_for(root))
            assert code == 2, (scope, result)
            c = check(result, "structure")
            assert c["ok"] is False
            assert c["reason"] == "missing field: owner"


# --- проверка 2: kind enum ---

def test_kind_not_in_enum_fails():
    with tempfile.TemporaryDirectory() as root:
        make_pkg(root, "DPF-BADKIND", kind="Something Else")
        result, code = resolve.run_verify("DPF-BADKIND", "local", levels_for(root))
        assert code == 2
        c = check(result, "kind")
        assert c["ok"] is False
        assert c["reason"] == "kind not in enum: Something Else"


# --- проверка 3: свежесть (гейтит только bank) ---

def test_stale_review_due_gates_bank_only():
    with tempfile.TemporaryDirectory() as root:
        make_pkg(root, "DPF-STALE", review_due="2000-01-01")

        result_local, code_local = resolve.run_verify("DPF-STALE", "local", levels_for(root))
        assert code_local == 0, result_local
        assert result_local["ok"] is True
        assert check(result_local, "freshness")["ok"] is False

        result_bank, code_bank = resolve.run_verify("DPF-STALE", "bank", levels_for(root))
        assert code_bank == 2
        assert result_bank["ok"] is False
        assert check(result_bank, "freshness")["ok"] is False


# --- проверка 4: критик-вердикт ---

def test_no_conformance_line_gates_bank_only():
    with tempfile.TemporaryDirectory() as root:
        make_pkg(root, "DPF-DRAFT", conformance=None)

        result_local, code_local = resolve.run_verify("DPF-DRAFT", "local", levels_for(root))
        assert code_local == 0, result_local
        assert result_local["ok"] is True
        assert check(result_local, "conformance")["ok"] is False

        result_bank, code_bank = resolve.run_verify("DPF-DRAFT", "bank", levels_for(root))
        assert code_bank == 2
        c = check(result_bank, "conformance")
        assert c["ok"] is False
        assert c["reason"] == "no admissible E.4.DPF.DA conformance line in DPF.md"


def test_repair_token_fails_conformance():
    with tempfile.TemporaryDirectory() as root:
        make_pkg(root, "DPF-REPAIR", conformance=REPAIR)
        result, code = resolve.run_verify("DPF-REPAIR", "bank", levels_for(root))
        assert code == 2
        assert check(result, "conformance")["ok"] is False


def test_verdict_read_from_dpf_md_not_references():
    # references несёт отрицательный токен, но DPF.md — положительный.
    # Читаем DPF.md → PASS (иначе false-positive/negative от references).
    negative_ref = (
        "ранний вердикт: "
        "E.4.DPF.DA: repairBeforeDPFUse; позже admissibleForDeclaredDPFUse "
        "не заявляется"
    )
    with tempfile.TemporaryDirectory() as root:
        make_pkg(root, "DPF-REFNEG", conformance=ADMISSIBLE, references=negative_ref)
        result, code = resolve.run_verify("DPF-REFNEG", "bank", levels_for(root))
        assert code == 0, result
        assert result["ok"] is True
        assert check(result, "conformance")["ok"] is True


def test_last_e4_line_wins_when_two_conformance_lines():
    # Как у DPF-COUPLING на диске: строка покрытия + строка вердикта.
    two_lines = (
        "> conformance: покрытие CC-DPF.1–9 — references/quality-record.md\n"
        + ADMISSIBLE
    )
    with tempfile.TemporaryDirectory() as root:
        make_pkg(root, "DPF-TWOLINE", conformance=two_lines)
        result, code = resolve.run_verify("DPF-TWOLINE", "bank", levels_for(root))
        assert code == 0, result
        assert check(result, "conformance")["ok"] is True


# --- executable-класс ---

def test_executable_pkg_with_apply_prompt_passes():
    with tempfile.TemporaryDirectory() as root:
        make_pkg(
            root,
            "LPF-EXEC",
            kind="Local Practice Framework",
            apply_prompt="применить стадию",
        )
        result, code = resolve.run_verify("LPF-EXEC", "bank", levels_for(root))
        assert code == 0, result
        assert result["ok"] is True


# --- вывод / формат ---

def test_json_shape():
    with tempfile.TemporaryDirectory() as root:
        make_pkg(root, "DPF-VALID")
        result, _ = resolve.run_verify("DPF-VALID", "bank", levels_for(root))
        assert set(result.keys()) == {"id", "scope", "checks", "ok"}
        assert result["id"] == "DPF-VALID"
        assert result["scope"] == "bank"
        for c in result["checks"]:
            assert set(c.keys()) == {"name", "ok", "reason"}


# --- CLI end-to-end (exit-коды + fail-closed) ---

def run_cli(project_root, *cli_args):
    env = dict(os.environ)
    home = tempfile.mkdtemp()
    env["HOME"] = home
    proc = subprocess.run(
        [sys.executable, SCRIPT, *cli_args],
        cwd=project_root,
        env=env,
        capture_output=True,
        text=True,
    )
    return proc


def test_non_utf8_dpf_md_does_not_crash_and_reports_unreadable():
    # ISSUE-004: не-UTF-8 DPF.md раньше давал необработанный UnicodeDecodeError
    # (exit 1, путался с «не найден»); теперь — аккуратный отказ с explicit reason.
    with tempfile.TemporaryDirectory() as project:
        fw = os.path.join(project, ".claude", "frameworks")
        pkg_dir = os.path.join(fw, "DPF-BAD")
        os.makedirs(pkg_dir)
        with open(os.path.join(pkg_dir, "DPF.md"), "wb") as fh:
            fh.write(b"---\ndpf_id: DPF-BAD\n---\n\xff\xfe garbage not utf8")

        info, code = resolve.run_verify("DPF-BAD", "bank", levels_for(fw))
        assert code == 2, info
        assert info["ok"] is False
        assert check(info, "resolve")["ok"] is True  # DPF.md найден, просто нечитаем

        cli = run_cli(project, "DPF-BAD")
        assert cli.returncode == 2, cli.stderr + cli.stdout
        assert "Traceback" not in cli.stderr, cli.stderr
        assert "unreadable DPF.md" in cli.stderr, cli.stderr


def test_cli_missing_local_exits_1_without_traceback():
    with tempfile.TemporaryDirectory() as project:
        missing = run_cli(project, "--verify", "DPF-NOPE", "--scope", "local")

        assert missing.returncode == 1, missing.stderr + missing.stdout
        assert "Traceback" not in missing.stderr, missing.stderr
        assert "verify: FAIL — not found: DPF-NOPE" in missing.stdout


def test_cli_bank_pass_and_fail():
    with tempfile.TemporaryDirectory() as project:
        fw = os.path.join(project, ".claude", "frameworks")
        os.makedirs(fw)
        make_pkg(fw, "DPF-VALID")
        make_pkg(fw, "DPF-DRAFT", conformance=None)

        ok = run_cli(project, "--verify", "DPF-VALID", "--scope", "bank")
        assert ok.returncode == 0, ok.stderr + ok.stdout
        assert "verify: PASS (scope=bank)" in ok.stdout

        fail = run_cli(project, "--verify", "DPF-DRAFT", "--scope", "bank")
        assert fail.returncode == 2, fail.stdout
        assert "verify: FAIL" in fail.stdout

        # тот же черновик под local-дефолтом проходит
        draft_local = run_cli(project, "--verify", "DPF-DRAFT")
        assert draft_local.returncode == 0, draft_local.stdout

        missing = run_cli(project, "--verify", "DPF-NOPE", "--scope", "bank")
        assert missing.returncode == 1, missing.stdout


def run_cli_with_home(project_root, home, *cli_args):
    env = dict(os.environ)
    env["HOME"] = home
    return subprocess.run(
        [sys.executable, SCRIPT, *cli_args],
        cwd=project_root,
        env=env,
        capture_output=True,
        text=True,
    )


def test_assessment_gates_package_regardless_of_source():
    # Правило пригодности перестало зависеть от происхождения пути: свод без
    # положительной оценки отклоняется и из человеческого списка тоже.
    for case, source_file, conformance, expected_code in (
        ("published_no_verdict", "frameworks.published", None, 2),
        ("published_repair_verdict", "frameworks.published", REPAIR, 2),
        ("published_admissible", "frameworks.published", ADMISSIBLE, 0),
        ("human_paths_no_verdict", ".dpf.paths", None, 2),
        ("human_paths_admissible", ".dpf.paths", ADMISSIBLE, 0),
    ):
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as project:
            root = os.path.join(home, "bank-frameworks")
            os.makedirs(root, exist_ok=True)
            make_pkg(root, "DPF-BANK", conformance=conformance)
            write_source_file(home, source_file, [root])

            proc = run_cli_with_home(project, home, "DPF-BANK")

            assert proc.returncode == expected_code, (
                f"{case}: код {proc.returncode}\n{proc.stdout}{proc.stderr}"
            )
            if expected_code == 2:
                assert "оценк" in (proc.stdout + proc.stderr), f"{case}: {proc.stderr}"


def test_verify_local_scope_stays_open_for_published_root():
    # Гейт основного пути и таблица областей --verify — разные договоры:
    # область local намеренно не гейтит допуск, и включение гейта на основном
    # пути её не меняет.
    with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as project:
        root = os.path.join(home, "bank-frameworks")
        os.makedirs(root, exist_ok=True)
        make_pkg(root, "DPF-BANK", conformance=None)
        write_source_file(home, "frameworks.published", [root])

        local = run_cli_with_home(project, home, "--verify", "DPF-BANK", "--scope", "local")
        bank = run_cli_with_home(project, home, "--verify", "DPF-BANK", "--scope", "bank")

        assert local.returncode == 0, local.stdout + local.stderr
        assert bank.returncode == 2, bank.stdout + bank.stderr


def test_list_marks_published_package_without_admissible_verdict():
    with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as project:
        root = os.path.join(home, "bank-frameworks")
        os.makedirs(root, exist_ok=True)
        make_pkg(root, "DPF-BANK", conformance=None)
        make_pkg(root, "DPF-OK", conformance=ADMISSIBLE)
        write_source_file(home, "frameworks.published", [root])

        proc = run_cli_with_home(project, home, "--list", "--json")

        assert proc.returncode == 0, proc.stderr
        rows = {row["id"]: row for row in json.loads(proc.stdout)}
        assert rows["DPF-BANK"]["published"] is True
        assert rows["DPF-BANK"]["admissible"] is False
        assert rows["DPF-OK"]["admissible"] is True


def test_legacy_bank_links_count_as_published_like_the_canonical_ones():
    # Каталог ссылок объявляет банк на обоих именах, поэтому поле не должно
    # меняться от того, прошёл перенос или нет.
    with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as project:
        bank = os.path.join(home, "bank", ".dpf")
        os.makedirs(bank)
        make_pkg(bank, "DPF-BANK")
        legacy_links = os.path.join(home, ".claude", "frameworks.d")
        os.makedirs(legacy_links)
        os.symlink(os.path.join(bank, "DPF-BANK"), os.path.join(legacy_links, "DPF-BANK"))

        proc = run_cli_with_home(project, home, "--list", "--json")

        assert proc.returncode == 0, proc.stderr
        rows = {row["id"]: row for row in json.loads(proc.stdout)}
        assert rows["DPF-BANK"]["published"] is True, rows["DPF-BANK"]


def write_source_file(home, name, lines):
    claude_dir = os.path.join(home, ".claude")
    os.makedirs(claude_dir, exist_ok=True)
    with open(os.path.join(claude_dir, name), "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def test_build_levels_reads_legacy_names_after_canonical_ones():
    with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as project:
        canonical_paths_root = os.path.join(home, "canonical-paths-root")
        legacy_paths_root = os.path.join(home, "legacy-paths-root")
        project_canonical = os.path.join(project, "canonical-project-root")
        project_legacy = os.path.join(project, "legacy-project-root")
        published_root = os.path.join(home, "published-root")
        write_project_source_file(project, ".dpf.paths", [project_canonical])
        write_project_source_file(project, "frameworks.paths", [project_legacy])
        write_source_file(home, ".dpf.paths", [canonical_paths_root])
        write_source_file(home, "frameworks.paths", [legacy_paths_root])
        write_source_file(home, "frameworks.published", [published_root])

        with mock.patch.dict(os.environ, {"HOME": home}):
            with mock.patch.object(resolve.os, "getcwd", return_value=project):
                levels = resolve.build_levels()

    assert levels == [
        ("project", os.path.join(project, ".claude", ".dpf")),
        ("project", project_canonical),
        ("project", os.path.join(project, ".claude", "frameworks")),
        ("project", project_legacy),
        ("user", os.path.join(home, ".claude", ".dpf")),
        ("user", os.path.join(home, ".claude", "frameworks")),
        ("plugin", canonical_paths_root),
        ("plugin", os.path.join(home, ".claude", "dpf.d")),
        ("plugin", legacy_paths_root),
        ("plugin", os.path.join(home, ".claude", "frameworks.d")),
        ("plugin", published_root),
    ]


def test_canonical_root_wins_over_legacy_root_with_same_id():
    with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as project:
        canonical = os.path.join(project, ".claude", ".dpf")
        legacy = os.path.join(project, ".claude", "frameworks")
        os.makedirs(canonical)
        os.makedirs(legacy)
        make_pkg(canonical, "DPF-SAME")
        make_pkg(legacy, "DPF-SAME")

        proc = run_cli_with_home(project, home, "DPF-SAME", "--json")

        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert json.loads(proc.stdout)["path"].startswith(os.path.realpath(canonical))


def test_legacy_source_in_use_names_the_migration_command():
    with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as project:
        legacy = os.path.join(project, ".claude", "frameworks")
        os.makedirs(legacy)
        make_pkg(legacy, "DPF-OLD")

        found = run_cli_with_home(project, home, "DPF-OLD")
        sources = run_cli_with_home(project, home, "--sources")

        assert found.returncode == 0, found.stdout + found.stderr
        assert "migrate_dpf_paths.py" in found.stderr, found.stderr
        assert "migrate_dpf_paths.py" in sources.stderr, sources.stderr


def test_canonical_layout_alone_says_nothing_about_migration():
    with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as project:
        canonical = os.path.join(project, ".claude", ".dpf")
        os.makedirs(canonical)
        make_pkg(canonical, "DPF-NEW")

        proc = run_cli_with_home(project, home, "DPF-NEW")

        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert proc.stderr == "", proc.stderr


def test_trusted_file_prefers_canonical_name_without_merging():
    for case, canonical_ids, legacy_ids, expected_code in (
        ("canonical_only", ["DPF-DRAFT"], None, 0),
        ("legacy_only", None, ["DPF-DRAFT"], 0),
        ("canonical_wins_over_legacy", [], ["DPF-DRAFT"], 2),
    ):
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as project:
            canonical = os.path.join(project, ".claude", ".dpf")
            os.makedirs(canonical)
            make_pkg(canonical, "DPF-DRAFT", conformance=None)
            if canonical_ids is not None:
                write_project_source_file(project, ".dpf.trusted", canonical_ids)
            if legacy_ids is not None:
                write_project_source_file(project, "frameworks.trusted", legacy_ids)

            proc = run_cli_with_home(project, home, "DPF-DRAFT")

            assert proc.returncode == expected_code, (
                f"{case}: код {proc.returncode}\n{proc.stdout}{proc.stderr}"
            )


def canonical_levels(home, project="/project", *plugin_roots):
    return [
        ("project", os.path.join(project, ".claude", ".dpf")),
        ("project", os.path.join(project, ".claude", "frameworks")),
        ("user", os.path.join(home, ".claude", ".dpf")),
        ("user", os.path.join(home, ".claude", "frameworks")),
        *plugin_roots,
    ]


def test_build_levels_includes_published_roots_after_paths():
    with tempfile.TemporaryDirectory() as home:
        paths_root = os.path.join(home, "paths-root")
        published_root = os.path.join(home, "published-root")
        write_source_file(home, ".dpf.paths", [paths_root])
        write_source_file(home, "frameworks.published", [published_root])

        with mock.patch.dict(os.environ, {"HOME": home}):
            with mock.patch.object(resolve.os, "getcwd", return_value="/project"):
                levels = resolve.build_levels()

    assert levels == canonical_levels(
        home,
        "/project",
        ("plugin", paths_root),
        ("plugin", os.path.join(home, ".claude", "dpf.d")),
        ("plugin", os.path.join(home, ".claude", "frameworks.d")),
        ("plugin", published_root),
    )


def test_build_levels_deduplicates_published_alias_after_human_path():
    with tempfile.TemporaryDirectory() as home:
        human_root = os.path.join(home, "human-root")
        published_alias = os.path.join(home, "published-alias")
        os.makedirs(human_root)
        os.symlink(human_root, published_alias)
        write_source_file(home, ".dpf.paths", [human_root])
        write_source_file(home, "frameworks.published", [published_alias])

        with mock.patch.dict(os.environ, {"HOME": home}):
            with mock.patch.object(resolve.os, "getcwd", return_value="/project"):
                levels = resolve.build_levels()

    assert levels == canonical_levels(
        home,
        "/project",
        ("plugin", human_root),
        ("plugin", os.path.join(home, ".claude", "dpf.d")),
        ("plugin", os.path.join(home, ".claude", "frameworks.d")),
    )


def test_build_levels_without_published_file_keeps_existing_levels():
    with tempfile.TemporaryDirectory() as home:
        paths_root = os.path.join(home, "paths-root")
        write_source_file(home, ".dpf.paths", [paths_root])

        with mock.patch.dict(os.environ, {"HOME": home}):
            with mock.patch.object(resolve.os, "getcwd", return_value="/project"):
                levels = resolve.build_levels()

    assert levels == canonical_levels(
        home,
        "/project",
        ("plugin", paths_root),
        ("plugin", os.path.join(home, ".claude", "dpf.d")),
        ("plugin", os.path.join(home, ".claude", "frameworks.d")),
    )


def write_project_source_file(project, name, lines):
    claude_dir = os.path.join(project, ".claude")
    os.makedirs(claude_dir, exist_ok=True)
    with open(os.path.join(claude_dir, name), "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def test_build_levels_reads_project_paths_before_user_level():
    with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as project:
        project_root = os.path.join(project, "dpf")
        user_paths_root = os.path.join(home, "paths-root")
        write_project_source_file(project, ".dpf.paths", [project_root])
        write_source_file(home, ".dpf.paths", [user_paths_root])

        with mock.patch.dict(os.environ, {"HOME": home}):
            with mock.patch.object(resolve.os, "getcwd", return_value=project):
                levels = resolve.build_levels()

    assert levels == [
        ("project", os.path.join(project, ".claude", ".dpf")),
        ("project", project_root),
        ("project", os.path.join(project, ".claude", "frameworks")),
        ("user", os.path.join(home, ".claude", ".dpf")),
        ("user", os.path.join(home, ".claude", "frameworks")),
        ("plugin", user_paths_root),
        ("plugin", os.path.join(home, ".claude", "dpf.d")),
        ("plugin", os.path.join(home, ".claude", "frameworks.d")),
    ]


def test_project_paths_root_resolves_package_without_touching_home():
    with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as project:
        project_root = os.path.join(project, "dpf")
        os.makedirs(project_root)
        make_pkg(project_root, "DPF-PROJECT")
        write_project_source_file(project, ".dpf.paths", ["dpf"])

        proc = run_cli_with_home(project, home, "DPF-PROJECT", "--json")

        assert proc.returncode == 0, proc.stdout + proc.stderr
        info = json.loads(proc.stdout)
        assert info["level"] == "project"
        assert not os.path.exists(os.path.join(home, ".claude", ".dpf.paths"))


def test_plugin_prefix_skips_project_declared_root():
    with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as project:
        project_root = os.path.join(project, "dpf")
        os.makedirs(project_root)
        make_pkg(project_root, "DPF-PROJECT")
        write_project_source_file(project, ".dpf.paths", [project_root])

        proc = run_cli_with_home(project, home, "plugin:DPF-PROJECT")

        assert proc.returncode == 1, proc.stdout + proc.stderr


def test_bank_directory_is_searched_without_manual_registration():
    with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as project:
        bank_frameworks = os.path.join(home, "bank", "frameworks")
        os.makedirs(bank_frameworks)
        make_pkg(bank_frameworks, "DPF-BANK")
        links_dir = os.path.join(home, ".claude", "dpf.d")
        os.makedirs(links_dir)
        os.symlink(os.path.join(bank_frameworks, "DPF-BANK"), os.path.join(links_dir, "DPF-BANK"))

        proc = run_cli_with_home(project, home, "DPF-BANK")

        assert proc.returncode == 0, proc.stdout + proc.stderr


def test_bank_directory_package_needs_admissible_verdict():
    with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as project:
        bank_frameworks = os.path.join(home, "bank", "frameworks")
        os.makedirs(bank_frameworks)
        make_pkg(bank_frameworks, "DPF-DRAFT", conformance=None)
        links_dir = os.path.join(home, ".claude", "dpf.d")
        os.makedirs(links_dir)
        os.symlink(os.path.join(bank_frameworks, "DPF-DRAFT"), os.path.join(links_dir, "DPF-DRAFT"))

        proc = run_cli_with_home(project, home, "DPF-DRAFT")

        assert proc.returncode == 2, proc.stdout + proc.stderr
        assert "оценка не записана" in (proc.stdout + proc.stderr)


def test_bank_owner_directory_is_not_listed_as_package():
    with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as project:
        bank_frameworks = os.path.join(home, "bank", "frameworks")
        os.makedirs(bank_frameworks)
        make_pkg(bank_frameworks, "DPF-BANK")
        owner_dir = os.path.join(home, ".claude", "dpf.d", ".fpf_banks", "demo-bank")
        os.makedirs(owner_dir)
        os.symlink(os.path.join(bank_frameworks, "DPF-BANK"), os.path.join(owner_dir, "DPF-BANK"))
        os.symlink(
            os.path.join(owner_dir, "DPF-BANK"),
            os.path.join(home, ".claude", "dpf.d", "DPF-BANK"),
        )

        proc = run_cli_with_home(project, home, "--list", "--json")

        assert proc.returncode == 0, proc.stderr
        rows = json.loads(proc.stdout)
        assert [row["id"] for row in rows] == ["DPF-BANK"]


def test_dangling_bank_link_does_not_resolve():
    with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as project:
        links_dir = os.path.join(home, ".claude", "dpf.d")
        os.makedirs(links_dir)
        os.symlink(os.path.join(home, "removed-plugin", "DPF-GONE"), os.path.join(links_dir, "DPF-GONE"))

        proc = run_cli_with_home(project, home, "DPF-GONE")

        assert proc.returncode == 1, proc.stdout + proc.stderr
        assert "Traceback" not in proc.stderr


def bank_link(home, package_dir, package_id):
    links_dir = os.path.join(home, ".claude", "dpf.d")
    os.makedirs(links_dir, exist_ok=True)
    os.symlink(package_dir, os.path.join(links_dir, package_id))


def test_same_package_gets_same_verdict_from_every_source():
    for case, place in (
        ("project", "project"),
        ("user_paths", "paths"),
        ("bank_links", "banks"),
        ("legacy_published", "published"),
    ):
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as project:
            root = os.path.join(home, "frameworks-root")
            os.makedirs(root, exist_ok=True)
            package = make_pkg(root, "DPF-DRAFT", conformance=None)
            if place == "project":
                write_project_source_file(project, ".dpf.paths", [root])
            elif place == "paths":
                write_source_file(home, ".dpf.paths", [root])
            elif place == "banks":
                bank_link(home, package, "DPF-DRAFT")
            else:
                write_source_file(home, "frameworks.published", [root])

            proc = run_cli_with_home(project, home, "DPF-DRAFT")

            assert proc.returncode == 2, f"{case}: код {proc.returncode}\n{proc.stdout}{proc.stderr}"
            assert "оценк" in (proc.stdout + proc.stderr), f"{case}: {proc.stderr}"


def write_trusted_file(project, ids):
    claude_dir = os.path.join(project, ".claude")
    os.makedirs(claude_dir, exist_ok=True)
    with open(os.path.join(claude_dir, "frameworks.trusted"), "w", encoding="utf-8") as handle:
        handle.write("\n".join(ids) + "\n")


def test_project_trust_admits_only_missing_verdict():
    for case, conformance, trusted, expected_code in (
        ("no_verdict_trusted", None, ["DPF-DRAFT"], 0),
        ("no_verdict_untrusted", None, [], 2),
        ("negative_verdict_trusted", REPAIR, ["DPF-DRAFT"], 2),
        ("unknown_token_trusted", "> conformance: E.4.DPF.DA: somethingElse", ["DPF-DRAFT"], 2),
        ("other_id_trusted", None, ["DPF-OTHER"], 2),
    ):
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as project:
            root = os.path.join(home, "frameworks-root")
            os.makedirs(root, exist_ok=True)
            package = make_pkg(root, "DPF-DRAFT", conformance=conformance)
            bank_link(home, package, "DPF-DRAFT")
            write_trusted_file(project, trusted)

            proc = run_cli_with_home(project, home, "DPF-DRAFT")

            assert proc.returncode == expected_code, (
                f"{case}: код {proc.returncode}\n{proc.stdout}{proc.stderr}"
            )


def test_project_trust_is_visible_in_output():
    with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as project:
        root = os.path.join(home, "frameworks-root")
        os.makedirs(root)
        package = make_pkg(root, "DPF-DRAFT", conformance=None)
        bank_link(home, package, "DPF-DRAFT")
        write_trusted_file(project, ["DPF-DRAFT"])

        as_json = run_cli_with_home(project, home, "DPF-DRAFT", "--json")
        human = run_cli_with_home(project, home, "DPF-DRAFT")

        assert as_json.returncode == 0, as_json.stdout + as_json.stderr
        info = json.loads(as_json.stdout)
        assert info["assessment"] == "absent"
        assert info["trusted_by_project"] is True
        assert info["admissible"] is False
        assert "доверию проекта" in human.stdout


def test_project_trust_requires_matching_internal_id():
    with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as project:
        root = os.path.join(home, "frameworks-root")
        os.makedirs(root)
        package = make_pkg(root, "DPF-DRAFT", dpf_id="DPF-RENAMED", conformance=None)
        bank_link(home, package, "DPF-DRAFT")
        write_trusted_file(project, ["DPF-DRAFT"])

        proc = run_cli_with_home(project, home, "DPF-DRAFT")

        assert proc.returncode == 2, proc.stdout + proc.stderr


def test_project_trust_does_not_reach_another_project():
    with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as trusting, \
            tempfile.TemporaryDirectory() as other:
        root = os.path.join(home, "frameworks-root")
        os.makedirs(root)
        package = make_pkg(root, "DPF-DRAFT", conformance=None)
        bank_link(home, package, "DPF-DRAFT")
        write_trusted_file(trusting, ["DPF-DRAFT"])

        assert run_cli_with_home(trusting, home, "DPF-DRAFT").returncode == 0
        assert run_cli_with_home(other, home, "DPF-DRAFT").returncode == 2


def test_project_trust_does_not_override_staleness_or_structure():
    for case, kwargs in (
        ("stale", {"review_due": "2000-01-01"}),
        ("not_active", {"status": "draft"}),
        ("missing_owner", {"owner": None}),
        ("unknown_kind", {"kind": "Something Else"}),
    ):
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as project:
            root = os.path.join(home, "frameworks-root")
            os.makedirs(root, exist_ok=True)
            package = make_pkg(root, "DPF-DRAFT", conformance=None, **kwargs)
            bank_link(home, package, "DPF-DRAFT")
            write_trusted_file(project, ["DPF-DRAFT"])

            proc = run_cli_with_home(project, home, "DPF-DRAFT")

            assert proc.returncode == 2, f"{case}: {proc.stdout}{proc.stderr}"


def test_broken_structure_is_rejected_even_with_positive_assessment():
    for case, kwargs in (
        ("id_mismatch", {"dpf_id": "DPF-RENAMED"}),
        ("missing_owner", {"owner": None}),
        ("unknown_kind", {"kind": "Something Else"}),
    ):
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as project:
            frameworks = os.path.join(project, ".claude", "frameworks")
            os.makedirs(frameworks, exist_ok=True)
            make_pkg(frameworks, "DPF-BROKEN", conformance=ADMISSIBLE, **kwargs)

            proc = run_cli_with_home(project, home, "DPF-BROKEN")

            assert proc.returncode == 2, f"{case}: код {proc.returncode}\n{proc.stdout}{proc.stderr}"

            listed = run_cli_with_home(project, home, "--list", "--json")
            row = json.loads(listed.stdout)[0]
            assert row["structure_problem"] is not None, case


def test_list_reports_assessment_for_every_level():
    with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as project:
        frameworks = os.path.join(project, ".claude", "frameworks")
        os.makedirs(frameworks)
        make_pkg(frameworks, "DPF-DRAFT", conformance=None)
        make_pkg(frameworks, "DPF-OK", conformance=ADMISSIBLE)
        make_pkg(frameworks, "DPF-REPAIR", conformance=REPAIR)

        proc = run_cli_with_home(project, home, "--list", "--json")

        assert proc.returncode == 0, proc.stderr
        rows = {row["id"]: row for row in json.loads(proc.stdout)}
        assert rows["DPF-OK"]["assessment"] == "admissible"
        assert rows["DPF-OK"]["admissible"] is True
        assert rows["DPF-DRAFT"]["assessment"] == "absent"
        assert rows["DPF-DRAFT"]["admissible"] is False
        assert rows["DPF-REPAIR"]["assessment"] == "rejected"
        assert rows["DPF-REPAIR"]["admissible"] is False


def test_sources_reports_missing_published_root_without_error():
    with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as project:
        missing_root = os.path.join(home, "missing-bank")
        write_source_file(home, "frameworks.published", [missing_root])
        env = dict(os.environ, HOME=home)
        result = subprocess.run(
            [sys.executable, SCRIPT, "--sources", "--json"],
            cwd=project,
            env=env,
            capture_output=True,
            text=True,
        )

    assert result.returncode == 0, result.stderr
    rows = json.loads(result.stdout)
    published = next(row for row in rows if row["origin"] == "published")
    assert published == {
        "level": "plugin",
        "origin": "published",
        "path": missing_root,
        "exists": False,
    }


def test_sources_human_reports_all_roots_with_origin_and_existence():
    with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as project:
        paths_root = os.path.join(home, "paths-root")
        missing_root = os.path.join(home, "missing-bank")
        os.makedirs(paths_root)
        write_source_file(home, ".dpf.paths", [paths_root])
        write_source_file(home, "frameworks.published", [missing_root])
        env = dict(os.environ, HOME=home)
        result = subprocess.run(
            [sys.executable, SCRIPT, "--sources"],
            cwd=project,
            env=env,
            capture_output=True,
            text=True,
        )

    assert result.returncode == 0, result.stderr
    rows = {}
    for line in result.stdout.splitlines():
        prefix, exists = line.rsplit(" exists=", 1)
        level, origin, path = prefix.split(maxsplit=2)
        rows[origin, path] = level, exists
    project_claude = os.path.join(os.path.realpath(project), ".claude")
    home_claude = os.path.join(home, ".claude")
    assert rows == {
        ("project", os.path.join(project_claude, ".dpf")): ("project", "no"),
        ("project-legacy", os.path.join(project_claude, "frameworks")): ("project", "no"),
        ("user", os.path.join(home_claude, ".dpf")): ("user", "no"),
        ("user-legacy", os.path.join(home_claude, "frameworks")): ("user", "no"),
        ("paths", paths_root): ("plugin", "yes"),
        ("banks", os.path.join(home_claude, "dpf.d")): ("plugin", "no"),
        ("banks-legacy", os.path.join(home_claude, "frameworks.d")): ("plugin", "no"),
        ("published", missing_root): ("plugin", "no"),
    }


def test_list_json_is_unchanged_without_published_file():
    with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as project:
        frameworks = os.path.join(project, ".claude", "frameworks")
        os.makedirs(frameworks)
        package = make_pkg(frameworks, "DPF-ONLY")
        env = dict(os.environ, HOME=home)
        result = subprocess.run(
            [sys.executable, SCRIPT, "--list", "--json"],
            cwd=project,
            env=env,
            capture_output=True,
            text=True,
        )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [
        {
            "id": "DPF-ONLY",
            "path": os.path.realpath(package),
            "level": "project",
            "kind": "Domain Principle Framework",
            "owner": "guardian",
            "status": "active",
            "review_due": "2099-01-01",
            "date": "",
            "executable": False,
            "stale": False,
            "stale_reason": None,
            # Происхождение пути больше не решает, применяется ли проверка:
            # состояние оценки приходит в выдачу для любого уровня.
            "published": False,
            "admissible": True,
            "assessment": "admissible",
            "trusted_by_project": False,
            "structure_problem": None,
            "shadowed": False,
        }
    ]


def _run_all():
    failures = []
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as exc:
                failures.append((name, exc))
                print(f"FAIL {name}: {exc}")
            except Exception as exc:  # noqa: BLE001
                failures.append((name, exc))
                print(f"ERROR {name}: {exc!r}")
    print(f"\n{len(failures)} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(_run_all())
