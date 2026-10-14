#!/usr/bin/env python3
"""Резолвер пакетов компетенций (DPF/LPF, FPF E.4.DPF) по уровням.

Уровни поиска (по приоритету, первый выигрывает при затенении):
  1. project  — $PWD/.claude/.dpf, затем корни построчно из
                $PWD/.claude/.dpf.paths (относительная строка читается от
                корня проекта)
  2. user     — ~/.claude/.dpf
  3. plugin   — пути построчно из ~/.claude/.dpf.paths, затем каталог ссылок
                банков ~/.claude/dpf.d (строки, начинающиеся с '#', и пустые
                строки пропускаются; отсутствующие файлы и каталоги просто не
                дают корней)

Прежние имена того же назначения читаются следом за каноническими внутри
своего уровня: .claude/frameworks и .claude/frameworks.paths у проекта,
~/.claude/frameworks у пользователя, ~/.claude/frameworks.paths,
~/.claude/frameworks.d и ~/.claude/frameworks.published на уровне подключённых
источников. Перенос на канонические имена выполняет отдельная команда
migrate_dpf_paths.py — сам резолвер ничего не переносит и не записывает.

Пакет = каталог <root>/<ID>/ с файлом DPF.md внутри. Полный id вида
"plugin:<ID>" минует уровни project/user и ищет только среди plugin-путей.

Только stdlib. Никаких внешних YAML-парсеров — читаем YAML-frontmatter
DPF.md простым построчным разбором `key: value` (формат авторингового
конвейера dpf-authoring: все нужные поля однострочные).

CLI:
  resolve.py <id> [--json]
  resolve.py --list [--json]
  resolve.py --sources [--json]

Exit-коды (для одиночного <id>):
  0 — пакет найден и пригоден
  1 — пакет не найден ни на одном уровне
  2 — пакет найден, но применять нельзя: нарушена форма, истёк срок
      (status!=active или review_due истёк/отсутствует/не парсится) либо нет
      положительной оценки E.4.DPF.DA — вывод содержит причину и владельца
      (owner) для эскалации (см. SKILL.md).

--list всегда завершается кодом 0 (информационный режим).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys


PACKAGES_DIRNAME = ".dpf"
PATHS_FILENAME = ".dpf.paths"
TRUSTED_FILENAME = ".dpf.trusted"
BANK_LINKS_DIRNAME = "dpf.d"
# Каталог владельцев внутри каталога ссылок: не свод, а служебная запись банка.
BANK_OWNERS_DIRNAME = ".fpf_banks"

# Прежние имена того же назначения. Читаются после канонических в пределах
# своего уровня, чтобы установка не теряла доступ до переноса. Переносит их
# отдельная команда, а не старт сессии.
LEGACY_PACKAGES_DIRNAME = "frameworks"
LEGACY_PATHS_FILENAME = "frameworks.paths"
LEGACY_TRUSTED_FILENAME = "frameworks.trusted"
LEGACY_BANK_LINKS_DIRNAME = "frameworks.d"
LEGACY_PUBLISHED_FILENAME = "frameworks.published"

MIGRATION_HINT = (
    "найдены своды по прежним путям (frameworks…); перенос выполняет отдельная "
    "команда: python3 <каталог скилла>/scripts/migrate_dpf_paths.py"
)


def read_lines(path: str) -> list[str]:
    """Непустые строки файла без комментариев. Нет файла — пустой список."""
    if not os.path.isfile(path):
        return []
    values = []
    with open(path, encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if line and not line.startswith("#"):
                values.append(line)
    return values


def read_source_paths(path: str) -> list[str]:
    return [os.path.expanduser(line) for line in read_lines(path)]


def project_declared_rows(project_claude_dir: str, filename: str, origin: str) -> list[tuple[str, str, str]]:
    # Относительная строка читается от корня проекта, а не от текущего каталога
    # процесса: иначе один и тот же файл давал бы разные корни при запуске из
    # подкаталога.
    project_root = os.path.dirname(project_claude_dir)
    return [
        ("project", origin, root if os.path.isabs(root) else os.path.join(project_root, root))
        for root in read_source_paths(os.path.join(project_claude_dir, filename))
    ]


def build_source_rows() -> list[tuple[str, str, str]]:
    home = os.path.expanduser("~")
    claude_dir = os.path.join(home, ".claude")
    project_claude_dir = os.path.join(os.getcwd(), ".claude")
    # Проектный список принадлежит репозиторию, поэтому его корни остаются
    # уровнем project: `plugin:<ID>` обязан миновать их так же, как каталог
    # сводов проекта. Прежние имена идут следом за каноническими внутри своего
    # уровня, поэтому перенос не меняет, какой уровень выигрывает.
    rows = [("project", "project", os.path.join(project_claude_dir, PACKAGES_DIRNAME))]
    rows.extend(project_declared_rows(project_claude_dir, PATHS_FILENAME, "project-paths"))
    rows.append(("project", "project-legacy", os.path.join(project_claude_dir, LEGACY_PACKAGES_DIRNAME)))
    rows.extend(project_declared_rows(project_claude_dir, LEGACY_PATHS_FILENAME, "project-paths-legacy"))

    rows.append(("user", "user", os.path.join(claude_dir, PACKAGES_DIRNAME)))
    rows.append(("user", "user-legacy", os.path.join(claude_dir, LEGACY_PACKAGES_DIRNAME)))

    rows.extend(("plugin", "paths", root) for root in read_source_paths(os.path.join(claude_dir, PATHS_FILENAME)))
    # Каталог ссылок банков объявлен самим резолвером: банк публикует в него
    # свои своды по одному и не переписывает ни чужие записи, ни человеческий
    # список путей.
    rows.append(("plugin", "banks", os.path.join(claude_dir, BANK_LINKS_DIRNAME)))
    rows.extend(
        ("plugin", "paths-legacy", root)
        for root in read_source_paths(os.path.join(claude_dir, LEGACY_PATHS_FILENAME))
    )
    rows.append(("plugin", "banks-legacy", os.path.join(claude_dir, LEGACY_BANK_LINKS_DIRNAME)))
    rows.extend(
        ("plugin", "published", root)
        for root in read_source_paths(os.path.join(claude_dir, LEGACY_PUBLISHED_FILENAME))
    )
    return rows


LEGACY_ORIGINS = frozenset(
    {
        "project-legacy",
        "project-paths-legacy",
        "user-legacy",
        "paths-legacy",
        "banks-legacy",
        "published",
    }
)


def legacy_sources_in_use() -> list[str]:
    """Прежние источники, которые сейчас действительно дают корни на диске."""
    return [
        root
        for _level, origin, root in build_source_rows()
        if origin in LEGACY_ORIGINS and os.path.isdir(root)
    ]


def warn_about_legacy_sources() -> None:
    roots = legacy_sources_in_use()
    if not roots:
        return
    print(f'{MIGRATION_HINT}\n  затронуто: {", ".join(roots)}', file=sys.stderr)


BANK_ORIGINS = frozenset({"published", "banks", "banks-legacy"})


def published_roots() -> set[str]:
    """Корни, объявленные хуком банка, а не человеком.

    Допуск свода от происхождения корня не зависит — его решает оценка. Это
    различение нужно выдаче: читателю важно, откуда свод взялся. Тот же корень,
    названный человеком в `.dpf.paths`, банковским не считается: ответственность
    за него взял человек. Прежний каталог ссылок различается наравне с новым,
    иначе поле меняло бы значение от одного лишь переноса.
    """
    published: set[str] = set()
    declared_by_human: set[str] = set()
    for _level, origin, root in build_source_rows():
        canonical = os.path.realpath(root)
        if origin in BANK_ORIGINS:
            if canonical not in declared_by_human:
                published.add(canonical)
        else:
            declared_by_human.add(canonical)
    return published


def build_levels() -> list[tuple[str, str]]:
    levels = []
    seen_roots = set()
    for level, _origin, root in build_source_rows():
        canonical_root = os.path.realpath(root)
        if canonical_root in seen_roots:
            continue
        seen_roots.add(canonical_root)
        levels.append((level, root))
    return levels


def parse_frontmatter(dpf_md_path: str) -> dict[str, str]:
    try:
        with open(dpf_md_path, encoding="utf-8") as handle:
            lines = handle.readlines()
    except (OSError, UnicodeError) as exc:
        print(f"unreadable DPF.md: {dpf_md_path}: {exc}", file=sys.stderr)
        return {}

    if not lines or lines[0].strip() != "---":
        return {}

    fields: dict[str, str] = {}
    for line in lines[1:]:
        stripped = line.rstrip("\n")
        if stripped.strip() == "---":
            break
        if not stripped.strip() or ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        key = key.strip()
        value = value.strip()
        if value.startswith('"') and value.endswith('"') and len(value) >= 2:
            value = value[1:-1]
        fields[key] = value
    return fields


def parse_list_value(value: str) -> list[str] | str:
    """Скобочный frontmatter-список ("[\"a\", \"b\"]") -> настоящий список для --json."""
    if not (value.startswith("[") and value.endswith("]")):
        return value
    items = []
    for part in value[1:-1].split(","):
        item = part.strip()
        if item.startswith('"') and item.endswith('"') and len(item) >= 2:
            item = item[1:-1]
        elif item.startswith("'") and item.endswith("'") and len(item) >= 2:
            item = item[1:-1]
        if item:
            items.append(item)
    return items


def check_stale(status: str, review_due: str) -> tuple[bool, str | None]:
    reasons = []
    if status != "active":
        reasons.append(f'status={status or "?"} (не active)')
    if not review_due:
        reasons.append("review_due отсутствует")
    else:
        try:
            due = dt.date.fromisoformat(review_due)
        except ValueError:
            reasons.append(f"review_due={review_due} не парсится как YYYY-MM-DD")
        else:
            if due < dt.date.today():
                reasons.append(f"review_due={review_due} истёк")
    if reasons:
        return True, "; ".join(reasons)
    return False, None


KIND_ENUM = {"Domain Principle Framework", "Local Practice Framework"}
REQUIRED_FIELDS = ("dpf_id", "kind", "status", "review_due", "owner")

# Гейтящие проверки по области: local-авторинг пропускает свежесть/вердикт;
# bank fail-closed гейтит всё. Ключ используют и run_verify, и печать финала.
GATING = {
    "local": ("resolve", "structure", "kind"),
    "bank": ("resolve", "structure", "kind", "freshness", "conformance"),
}

_CONFORMANCE_MARKER = "E.4.DPF.DA:"
_ADMISSIBLE_TOKEN = "admissibleForDeclaredDPFUse"

ASSESSMENT_ADMISSIBLE = "admissible"
ASSESSMENT_ABSENT = "absent"
ASSESSMENT_REJECTED = "rejected"
ASSESSMENT_UNREADABLE = "unreadable"


def read_conformance_verdict(dpf_md_path: str) -> tuple[bool, str | None]:
    """Читает авторитетный вердикт E.4.DPF.DA из самого DPF.md.

    Источник истины — ПОСЛЕДНЯЯ строка '> conformance:', несущая маркер
    'E.4.DPF.DA:'; статус — токен сразу за маркером. references/ не сканируется:
    там несколько вердиктов разных раундов и токен встречается в отрицаниях
    (false-positive). admissible только если токен ровно admissibleForDeclaredDPFUse.
    """
    admissible, _assessment, token = read_assessment(dpf_md_path)
    return admissible, token


def read_assessment(dpf_md_path: str) -> tuple[bool, str, str | None]:
    """Состояние оценки свода: положительная, отсутствует, иная.

    Три исхода различимы, потому что отменить проектным доверием можно только
    отсутствие оценки. Нечитаемый файл к отсутствию оценки не приравнивается:
    это неизвестное состояние, и доверие его не покрывает.
    """
    try:
        with open(dpf_md_path, encoding="utf-8") as handle:
            lines = handle.readlines()
    except (OSError, UnicodeError) as exc:
        print(f"unreadable DPF.md: {dpf_md_path}: {exc}", file=sys.stderr)
        return False, ASSESSMENT_UNREADABLE, None
    verdict_line = None
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("> conformance:") and _CONFORMANCE_MARKER in stripped:
            verdict_line = stripped
    if verdict_line is None:
        return False, ASSESSMENT_ABSENT, None
    after = verdict_line.split(_CONFORMANCE_MARKER, 1)[1].split()
    token = after[0] if after else ""
    if token == _ADMISSIBLE_TOKEN:
        return True, ASSESSMENT_ADMISSIBLE, token
    return False, ASSESSMENT_REJECTED, token or None


def read_trusted_ids() -> set[str]:
    """Идентификаторы из проектного `.claude/.dpf.trusted`.

    Список принимает проект и только для себя: глобального файла нет намеренно.
    """
    claude_dir = os.path.join(os.getcwd(), ".claude")
    canonical = os.path.join(claude_dir, TRUSTED_FILENAME)
    # Прежний файл читается, только когда нового нет: два списка объединять
    # молча нельзя — доверие объявляет проект, и объединение скрыло бы, какой
    # именно список действует.
    if os.path.isfile(canonical):
        return set(read_lines(canonical))
    return set(read_lines(os.path.join(claude_dir, LEGACY_TRUSTED_FILENAME)))


def run_verify(id_arg: str, scope: str, levels: list[tuple[str, str]]) -> tuple[dict, int]:
    checks: list[dict] = []
    info, _ = resolve_id(id_arg, levels)
    checks.append({"name": "resolve", "ok": info is not None,
                   "reason": None if info is not None else f"not found: {id_arg}"})
    if info is None:
        return {"id": id_arg, "scope": scope, "checks": checks, "ok": False}, 1

    dpf_md = os.path.join(info["path"], "DPF.md")
    fm = parse_frontmatter(dpf_md)

    missing = next((name for name in REQUIRED_FIELDS if not fm.get(name, "").strip()), None)
    declared_id = fm.get("dpf_id", "").strip()
    directory_id = os.path.basename(os.path.normpath(info["path"]))
    if missing is None and declared_id != directory_id:
        missing_reason = f"dpf_id={declared_id} не совпадает с каталогом {directory_id}"
    else:
        missing_reason = None if missing is None else f"missing field: {missing}"
    checks.append({"name": "structure", "ok": missing_reason is None, "reason": missing_reason})

    kind = fm.get("kind", "").strip()
    kind_ok = kind in KIND_ENUM
    checks.append({"name": "kind", "ok": kind_ok,
                   "reason": None if kind_ok else f"kind not in enum: {kind}"})

    stale, stale_reason = check_stale(fm.get("status", "").strip(), fm.get("review_due", "").strip())
    checks.append({"name": "freshness", "ok": not stale, "reason": stale_reason})

    admissible, _token = read_conformance_verdict(dpf_md)
    checks.append({"name": "conformance", "ok": admissible,
                   "reason": None if admissible else "no admissible E.4.DPF.DA conformance line in DPF.md"})

    gating = GATING[scope]
    overall_ok = all(c["ok"] for c in checks if c["name"] in gating)
    return {"id": id_arg, "scope": scope, "checks": checks, "ok": overall_ok}, (0 if overall_ok else 2)


def structure_problem(pkg_id: str, fm: dict[str, str]) -> str | None:
    """Первое нарушение обязательной формы свода или None."""
    missing = next((name for name in REQUIRED_FIELDS if not fm.get(name, "").strip()), None)
    if missing is not None:
        return f"в DPF.md нет обязательного поля {missing}"
    kind = fm.get("kind", "").strip()
    if kind not in KIND_ENUM:
        return f"kind вне допустимого набора: {kind}"
    declared_id = fm.get("dpf_id", "").strip()
    if declared_id != pkg_id:
        return f"dpf_id={declared_id} не совпадает с именем каталога {pkg_id}"
    return None


def build_info(
    pkg_id: str, pkg_dir: str, level_name: str, published: set[str] | None = None,
    trusted: set[str] | None = None,
) -> dict:
    dpf_md = os.path.join(pkg_dir, "DPF.md")
    fm = parse_frontmatter(dpf_md)
    status = fm.get("status", "")
    review_due = fm.get("review_due", "")
    stale, reason = check_stale(status, review_due)
    executable = os.path.isfile(os.path.join(pkg_dir, "assets", "apply-prompt.md"))
    # Наборы считаются сами, если их не передали: забытый аргумент обязан
    # приводить к проверке, а не к её обходу.
    roots = published_roots() if published is None else published
    trusted_ids = read_trusted_ids() if trusted is None else trusted
    from_published = os.path.realpath(os.path.dirname(pkg_dir)) in roots
    admissible, assessment, _token = read_assessment(dpf_md)
    structure = structure_problem(pkg_id, fm)
    # Доверие проекта отменяет только отсутствие оценки и только при точном
    # совпадении имени каталога с идентификатором внутри свода. Отрицательная
    # или нечитаемая оценка, сломанная форма и просрочка остаются отказом.
    trusted_by_project = (
        assessment == ASSESSMENT_ABSENT and structure is None and pkg_id in trusted_ids
    )
    return {
        "published": from_published,
        "admissible": admissible,
        "assessment": assessment,
        "trusted_by_project": trusted_by_project,
        "structure_problem": structure,
        "id": fm.get("dpf_id", pkg_id),
        "path": pkg_dir,
        "level": level_name,
        "kind": fm.get("kind", ""),
        "owner": parse_list_value(fm.get("owner", "")),
        "status": status,
        "review_due": review_due,
        "date": fm.get("date", ""),
        "executable": executable,
        "stale": stale,
        "stale_reason": reason,
    }


def admission_problem(info: dict) -> str | None:
    """Почему свод нельзя применять. None — можно.

    Правило одно для всех уровней: происхождение пути не меняет ни форму, ни
    свежесть, ни состояние оценки.
    """
    if info["structure_problem"] is not None:
        return info["structure_problem"]
    if info["stale"]:
        return info["stale_reason"]
    if info["admissible"] or info["trusted_by_project"]:
        return None
    if info["assessment"] == ASSESSMENT_ABSENT:
        return (
            "оценка не записана: в DPF.md нет строки E.4.DPF.DA. Проект может "
            "назвать этот свод в .claude/.dpf.trusted, если работает с "
            "черновиком осознанно"
        )
    if info["assessment"] == ASSESSMENT_UNREADABLE:
        return "оценка не прочитана: DPF.md недоступен или не в UTF-8"
    return "оценка отрицательная: строка E.4.DPF.DA не допускает применение"


def resolve_id(id_arg: str, levels: list[tuple[str, str]]) -> tuple[dict | None, list[str]]:
    if id_arg.startswith("plugin:"):
        bare_id = id_arg[len("plugin:") :]
        search_levels = [(lvl, root) for lvl, root in levels if lvl == "plugin"]
    else:
        bare_id = id_arg
        search_levels = levels

    searched = []
    roots = published_roots()
    trusted = read_trusted_ids()
    for level_name, root in search_levels:
        searched.append(f"{level_name}:{root}")
        pkg_dir = os.path.join(root, bare_id)
        if os.path.isfile(os.path.join(pkg_dir, "DPF.md")):
            return build_info(bare_id, pkg_dir, level_name, roots, trusted), searched
    return None, searched


def iter_packages(root: str):
    if not os.path.isdir(root):
        return
    for name in sorted(os.listdir(root)):
        pkg_dir = os.path.join(root, name)
        if os.path.isfile(os.path.join(pkg_dir, "DPF.md")):
            yield name, pkg_dir


def list_all(levels: list[tuple[str, str]]) -> list[dict]:
    seen: dict[str, str] = {}
    rows: list[dict] = []
    roots = published_roots()
    trusted = read_trusted_ids()
    for level_name, root in levels:
        for pkg_id, pkg_dir in iter_packages(root):
            shadowed = pkg_id in seen
            info = build_info(pkg_id, pkg_dir, level_name, roots, trusted)
            info["shadowed"] = shadowed
            if not shadowed:
                seen[pkg_id] = pkg_dir
            rows.append(info)
    return rows


def list_sources() -> list[dict]:
    return [
        {
            "level": level,
            "origin": origin,
            "path": root,
            "exists": os.path.isdir(root),
        }
        for level, origin, root in build_source_rows()
    ]


ASSESSMENT_TEXT = {
    ASSESSMENT_ADMISSIBLE: "положительная",
    ASSESSMENT_ABSENT: "не записана",
    ASSESSMENT_REJECTED: "отрицательная",
    ASSESSMENT_UNREADABLE: "не прочитана",
}


def assessment_text(info: dict) -> str:
    text = ASSESSMENT_TEXT[info["assessment"]]
    if info["trusted_by_project"]:
        # Доверие проекта — не заключение оценщика и не разрешение на любое
        # применение: оно лишь допускает работу с неоценённым сводом здесь.
        return f"{text}; пропущен по доверию проекта"
    return text


def print_info_human(info: dict) -> None:
    print(info["id"])
    print(f'  path:        {info["path"]}')
    print(f'  level:       {info["level"]}')
    print(f'  kind:        {info["kind"] or "?"}')
    owner = info["owner"]
    owner_text = ", ".join(owner) if isinstance(owner, list) else owner
    print(f'  owner:       {owner_text or "?"}')
    print(f'  status:      {info["status"] or "?"}')
    print(f'  review_due:  {info["review_due"] or "?"}')
    executable_note = "assets/apply-prompt.md найден" if info["executable"] else "ground-only, assets/apply-prompt.md отсутствует"
    print(f'  executable:  {"да" if info["executable"] else "нет"} ({executable_note})')
    print(f'  fresh:       {"нет" if info["stale"] else "да"}')
    if info["stale"]:
        print(f'  stale_reason: {info["stale_reason"]}')
    print(f"  оценка:      {assessment_text(info)}")


def print_list_human(rows: list[dict]) -> None:
    if not rows:
        print("(пакетов не найдено ни на одном уровне)")
        return
    for row in rows:
        shadow_note = " [shadowed]" if row["shadowed"] else ""
        stale_note = " [stale]" if row["stale"] else ""
        if row["trusted_by_project"]:
            admission_note = " [по доверию проекта]"
        elif admission_problem(row) is not None:
            admission_note = " [без допуска]"
        else:
            admission_note = ""
        print(f'{row["id"]:<32} {row["level"]:<8} {row["kind"]:<28} {row["status"]:<10}{shadow_note}{stale_note}{admission_note}')


def print_sources_human(rows: list[dict]) -> None:
    for row in rows:
        exists = "yes" if row["exists"] else "no"
        print(f'{row["level"]:<8} {row["origin"]:<9} {row["path"]} exists={exists}')


def print_verify_human(result: dict) -> None:
    for c in result["checks"]:
        status = "PASS" if c["ok"] else "FAIL"
        suffix = f"  {c['reason']}" if c["reason"] else ""
        print(f"{status}  {c['name']}{suffix}")
    if result["ok"]:
        print(f'verify: PASS (scope={result["scope"]})')
    else:
        gating = GATING[result["scope"]]
        first = next(c["reason"] for c in result["checks"] if c["name"] in gating and not c["ok"])
        print(f"verify: FAIL — {first}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Резолвер пакетов компетенций (DPF/LPF).")
    parser.add_argument("id", nargs="?", help="id пакета, опц. с префиксом plugin:")
    parser.add_argument("--list", action="store_true", help="показать слитую карту по всем уровням")
    parser.add_argument("--sources", action="store_true", help="показать источники уровней")
    parser.add_argument("--verify", action="store_true", help="проверить пригодность пакета (гейт)")
    parser.add_argument("--scope", choices=["local", "bank"], default="local",
                        help="область гейта для --verify (дефолт local)")
    parser.add_argument("--json", action="store_true", help="вывод в JSON")
    args = parser.parse_args()

    levels = build_levels()
    # Подсказка идёт в stderr и не меняет ни выдачу, ни код возврата: перенос —
    # отдельное решение человека, а не побочный итог обычного вызова.
    warn_about_legacy_sources()

    if args.verify:
        if not args.id:
            parser.error("нужен <id> для --verify")
        result, code = run_verify(args.id, args.scope, levels)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print_verify_human(result)
        return code

    if args.sources:
        rows = list_sources()
        if args.json:
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        else:
            print_sources_human(rows)
        return 0

    if args.list:
        rows = list_all(levels)
        if args.json:
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        else:
            print_list_human(rows)
        return 0

    if not args.id:
        parser.error("нужен <id> либо --list")

    info, searched = resolve_id(args.id, levels)

    if info is None:
        if args.json:
            print(json.dumps({"id": args.id, "found": False, "searched": searched}, ensure_ascii=False, indent=2))
        else:
            print(f"не найден: {args.id}", file=sys.stderr)
            print(f'  искали в: {", ".join(searched)}', file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        print_info_human(info)

    problem = admission_problem(info)
    if problem is not None:
        print(f"свод применять нельзя: {args.id} — {problem}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
