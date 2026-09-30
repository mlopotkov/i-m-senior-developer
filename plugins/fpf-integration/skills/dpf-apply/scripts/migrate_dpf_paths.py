#!/usr/bin/env python3
"""Перенос сводов и настроек на канонические имена путей.

Прежние имена (`frameworks`, `frameworks.paths`, `frameworks.trusted`,
`frameworks.d`) резолвер продолжает читать, поэтому перенос — отдельное решение
человека, а не побочный итог старта сессии. Без `--apply` команда ничего не
пишет: она печатает список предстоящих операций.

Договор безопасности: команда сначала проверяет весь план целиком и отказывает
целиком, если хотя бы одна операция небезопасна — занятое имя назначения,
чужая ссылка банка, нечитаемая запись. Частичного переноса не бывает, потому
что наполовину перенесённая установка хуже любой из двух целых.

Не переносит `~/.claude/frameworks.published`: строки в нём принадлежат
банкам, и заменить их может только владелец банка при следующем запуске. Файл
попадает в отчёт как то, что человек закрывает сам.

CLI:
  migrate_dpf_paths.py [--project <путь>] [--home <путь>] [--apply]

Коды возврата:
  0  — план показан или выполнен
  3  — операция небезопасна, ничего не изменено
  64 — неверный вызов
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import NoReturn

EXIT_OK = 0
EXIT_REFUSED = 3
EXIT_USAGE = 64

PACKAGES_DIRNAME = ".dpf"
PATHS_FILENAME = ".dpf.paths"
TRUSTED_FILENAME = ".dpf.trusted"
BANK_LINKS_DIRNAME = "dpf.d"
BANK_OWNERS_DIRNAME = ".fpf_banks"

LEGACY_PACKAGES_DIRNAME = "frameworks"
LEGACY_PATHS_FILENAME = "frameworks.paths"
LEGACY_TRUSTED_FILENAME = "frameworks.trusted"
LEGACY_BANK_LINKS_DIRNAME = "frameworks.d"
LEGACY_PUBLISHED_FILENAME = "frameworks.published"
# Прежний каталог владельцев назывался иначе; обе формы встречаются на диске.
LEGACY_OWNERS_DIRNAMES = (".fpf_banks", ".banks")


class MigrationParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(EXIT_USAGE, f"{self.prog}: ошибка: {message}\n")


class Plan:
    """Операции переноса и причины отказа, собранные до любой записи."""

    def __init__(self) -> None:
        self.moves: list[tuple[Path, Path]] = []
        self.links: list[tuple[Path, Path, str]] = []
        self.rewrites: list[tuple[Path, Path, list[str]]] = []
        self.removals: list[Path] = []
        self.notes: list[str] = []
        self.refusals: list[str] = []

    @property
    def empty(self) -> bool:
        return not (self.moves or self.links or self.rewrites or self.removals)


def read_lines(path: Path) -> list[str]:
    if not path.is_file():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]


def plan_move(plan: Plan, source: Path, destination: Path, what: str) -> bool:
    if not os.path.lexists(source):
        return False
    if os.path.lexists(destination):
        plan.refusals.append(
            f"{what}: {destination} уже существует, перенос {source} не выполняется"
        )
        return False
    plan.moves.append((source, destination))
    return True


def plan_roots_and_files(plan: Plan, claude_dir: Path, *, with_trusted: bool) -> dict[str, Path]:
    """Каталог сводов и файлы настройки одного уровня."""
    migrated: dict[str, Path] = {}
    source = claude_dir / LEGACY_PACKAGES_DIRNAME
    destination = claude_dir / PACKAGES_DIRNAME
    if plan_move(plan, source, destination, "каталог сводов"):
        migrated[str(source.resolve())] = destination

    plan_move(plan, claude_dir / LEGACY_PATHS_FILENAME, claude_dir / PATHS_FILENAME, "список путей")
    if with_trusted:
        plan_move(
            plan,
            claude_dir / LEGACY_TRUSTED_FILENAME,
            claude_dir / TRUSTED_FILENAME,
            "список доверия",
        )
    return migrated


def plan_path_rewrites(plan: Plan, claude_dir: Path, migrated: dict[str, Path]) -> None:
    """Строки списков путей, указывающие на перенесённые каталоги."""
    for source_name, destination_name in (
        (LEGACY_PATHS_FILENAME, PATHS_FILENAME),
        (PATHS_FILENAME, PATHS_FILENAME),
    ):
        source = claude_dir / source_name
        if not source.is_file():
            continue
        lines = read_lines(source)
        updated = []
        changed = False
        for line in lines:
            if not line or line.startswith("#"):
                updated.append(line)
                continue
            expanded = Path(os.path.expanduser(line))
            key = str(expanded.resolve()) if expanded.exists() else str(expanded)
            if key in migrated:
                updated.append(str(migrated[key]))
                changed = True
            else:
                updated.append(line)
        if changed:
            plan.rewrites.append((source, claude_dir / destination_name, updated))
        break


def link_owner(link_path: Path, links_dir: Path) -> str | None:
    """Имя банка-владельца плоской ссылки или None для чужой записи."""
    if not link_path.is_symlink():
        return None
    target = Path(os.readlink(link_path))
    if not target.is_absolute():
        target = link_path.parent / target
    parts = Path(os.path.normpath(target)).parts
    root_parts = Path(os.path.normpath(links_dir)).parts
    if parts[: len(root_parts)] != root_parts:
        return None
    rest = parts[len(root_parts) :]
    if len(rest) < 3 or rest[0] not in LEGACY_OWNERS_DIRNAMES:
        return None
    return rest[1]


def plan_bank_links(plan: Plan, claude_dir: Path) -> None:
    legacy_links = claude_dir / LEGACY_BANK_LINKS_DIRNAME
    if not legacy_links.is_dir():
        return
    new_links = claude_dir / BANK_LINKS_DIRNAME
    for entry in sorted(legacy_links.iterdir()):
        if entry.name in LEGACY_OWNERS_DIRNAMES:
            continue
        owner = link_owner(entry, legacy_links)
        if owner is None:
            plan.refusals.append(
                f"ссылка {entry} не принадлежит известному банку: перенос отменён, "
                "перенесите её сами или удалите"
            )
            continue
        owner_source = None
        for owners_dirname in LEGACY_OWNERS_DIRNAMES:
            candidate = legacy_links / owners_dirname / owner / entry.name
            if os.path.lexists(candidate):
                owner_source = candidate
                break
        if owner_source is None:
            plan.refusals.append(f"у ссылки {entry} нет записи владельца: перенос отменён")
            continue
        owner_target = os.readlink(owner_source) if owner_source.is_symlink() else str(owner_source)
        owner_destination = new_links / BANK_OWNERS_DIRNAME / owner / entry.name
        flat_destination = new_links / entry.name
        if os.path.lexists(owner_destination) or os.path.lexists(flat_destination):
            plan.refusals.append(
                f"свод {entry.name} уже опубликован в {new_links}: перенос отменён"
            )
            continue
        plan.links.append((owner_destination, Path(owner_target), "owner"))
        plan.links.append(
            (
                flat_destination,
                Path(os.path.join(BANK_OWNERS_DIRNAME, owner, entry.name)),
                "flat",
            )
        )
        plan.removals.append(entry)
        plan.removals.append(owner_source)


def build_plan(project: Path, home: Path) -> Plan:
    plan = Plan()
    project_claude = project / ".claude"
    home_claude = home / ".claude"

    migrated = plan_roots_and_files(plan, project_claude, with_trusted=True)
    migrated.update(plan_roots_and_files(plan, home_claude, with_trusted=False))
    plan_path_rewrites(plan, project_claude, migrated)
    plan_path_rewrites(plan, home_claude, migrated)
    plan_bank_links(plan, home_claude)

    published = home_claude / LEGACY_PUBLISHED_FILENAME
    if published.is_file():
        plan.notes.append(
            f"{published} оставлен как есть: строки в нём принадлежат банкам, "
            "и обновляет их сам банк при следующем запуске"
        )
    return plan


def describe(plan: Plan) -> str:
    lines: list[str] = []
    for source, destination in plan.moves:
        lines.append(f"перенести: {source} → {destination}")
    for destination, target, kind in plan.links:
        lines.append(f"создать ссылку ({kind}): {destination} → {target}")
    for source, destination, _ in plan.rewrites:
        lines.append(f"переписать строки списка путей: {source} → {destination}")
    for path in plan.removals:
        lines.append(f"удалить прежнюю ссылку: {path}")
    for note in plan.notes:
        lines.append(f"замечание: {note}")
    for refusal in plan.refusals:
        lines.append(f"ОТКАЗ: {refusal}")
    if plan.empty and not plan.refusals:
        lines.append("переносить нечего: установка уже на канонических путях")
    return "\n".join(lines)


def apply_plan(plan: Plan) -> None:
    for source, destination in plan.moves:
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.rename(source, destination)
    for destination, target, _kind in plan.links:
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(target, destination)
    for source, destination, lines in plan.rewrites:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
        # Прежнее имя могло уже уехать операцией переноса выше: тогда удалять
        # нечего, и это не ошибка.
        if source != destination:
            source.unlink(missing_ok=True)
    for path in plan.removals:
        path.unlink(missing_ok=True)
    # Пустой прежний каталог ссылок убирается только когда в нём ничего не
    # осталось: чужие записи — не наше дело.
    for path in plan.removals:
        parent = path.parent
        while parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent


def main(argv: list[str] | None = None) -> int:
    parser = MigrationParser(description="Перенос сводов на канонические имена путей.")
    parser.add_argument("--project", type=Path, default=Path.cwd(), help="корень проекта")
    parser.add_argument("--home", type=Path, default=Path.home(), help="домашний каталог")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="выполнить перенос; без него команда только показывает план",
    )
    options = parser.parse_args(argv)
    project = options.project.expanduser()
    home = options.home.expanduser()
    if not project.is_dir():
        parser.error(f"нет каталога проекта {project}")
    if not home.is_dir():
        parser.error(f"нет домашнего каталога {home}")

    plan = build_plan(project, home)
    print(describe(plan))

    if plan.refusals:
        print("ничего не изменено: сначала устраните причины отказа")
        return EXIT_REFUSED
    if not options.apply:
        if not plan.empty:
            print("это только план; выполнить перенос: тот же вызов с --apply")
        return EXIT_OK

    apply_plan(plan)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
