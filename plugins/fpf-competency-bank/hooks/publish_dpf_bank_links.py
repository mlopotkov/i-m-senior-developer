#!/usr/bin/env python3
"""Публикация сводов банка в общий каталог ссылок ~/.claude/dpf.d.

Каждый свод банка получает собственную ссылку, поэтому два банка сосуществуют:
запись одного не затрагивает записи другого. Владение различимо по цели плоской
ссылки — она ведёт в собственный каталог банка `.fpf_banks/<имя банка>/<ID>`, а уже
его ссылка указывает на каталог текущей версии плагина. Поэтому владелец
плоской ссылки остаётся определим и после удаления прежней версии плагина, на
которую она когда-то указывала.

Чужая запись не захватывается: при совпадении идентификатора хук называет
причину и оставляет запись владельца нетронутой. Свои ссылки на своды, которых
больше нет в поставке, удаляются.

Общий файл ~/.claude/frameworks.published этот хук больше не пишет: он
оставался единственной строкой на весь каталог и вытеснял второй банк.
Резолвер продолжает читать прежний файл и прежний каталог ссылок
~/.claude/frameworks.d, поэтому установка до переноса доступ к сводам не
теряет. Сам перенос выполняет отдельная команда migrate_dpf_paths.py: старт
сессии чужие данные не трогает.

Хук не блокирует старт сессии: причина печатается в stderr, код возврата
всегда 0. Удалённый плагин собственный хук запустить не может, поэтому уборку
своих ссылок после удаления хук не обещает — она выполняется этим же файлом при
следующем запуске оставшихся банков только для их собственных записей.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

BANK_NAME = "fpf-competency-bank"
PACKAGES_DIRNAME = ".dpf"
LINKS_DIRNAME = "dpf.d"
OWNERS_DIRNAME = ".fpf_banks"


def shipped_package_ids(packages_dir: Path) -> list[str]:
    if not packages_dir.is_dir():
        return []
    return sorted(
        entry.name
        for entry in packages_dir.iterdir()
        if (entry / "DPF.md").is_file()
    )


def replace_symlink(link_path: Path, target: str) -> None:
    """Атомарная замена ссылки: временное имя рядом, затем os.replace."""
    temporary_path = Path(
        tempfile.mkdtemp(dir=link_path.parent, prefix=".publish-")
    ) / link_path.name
    try:
        os.symlink(target, temporary_path)
        os.replace(temporary_path, link_path)
    finally:
        if temporary_path.is_symlink() or temporary_path.exists():
            temporary_path.unlink(missing_ok=True)
        temporary_path.parent.rmdir()


def owned_by_bank(link_path: Path, owner_dir: Path) -> bool:
    """Наша ли запись. Цель читается без разыменования: пропавшая версия
    плагина не должна превращать нашу ссылку в чужую."""
    if not link_path.is_symlink():
        return False
    target = Path(os.readlink(link_path))
    if not target.is_absolute():
        target = link_path.parent / target
    # Путь нормализуется без разыменования: ссылка владельца ведёт в каталог
    # версии плагина, и на удалённой версии разыменование потеряло бы владельца.
    return Path(os.path.normpath(owner_dir)) in Path(os.path.normpath(target)).parents


def publish(plugin_root: Path, claude_dir: Path) -> list[str]:
    problems: list[str] = []
    packages_dir = plugin_root / PACKAGES_DIRNAME
    package_ids = shipped_package_ids(packages_dir)
    if not package_ids:
        return [f"В поставке банка нет сводов: {packages_dir}"]

    links_dir = claude_dir / LINKS_DIRNAME
    owner_dir = links_dir / OWNERS_DIRNAME / BANK_NAME
    owner_dir.mkdir(parents=True, exist_ok=True)

    for package_id in package_ids:
        replace_symlink(owner_dir / package_id, str(packages_dir / package_id))

    # Карта компетенций банка лежит рядом со сводами, а не внутри каждого:
    # подсказка по ключевым словам читает её у владельца ссылки.
    competency_map = packages_dir / "competency-map.md"
    if competency_map.is_file():
        replace_symlink(owner_dir / competency_map.name, str(competency_map))

    for stale in sorted(owner_dir.iterdir()):
        if stale.name not in package_ids and stale.name != competency_map.name:
            stale.unlink(missing_ok=True)

    for package_id in package_ids:
        link_path = links_dir / package_id
        if os.path.lexists(link_path) and not owned_by_bank(link_path, owner_dir):
            problems.append(
                f"Свод {package_id} уже опубликован другой записью "
                f"{link_path}; запись не заменена."
            )
            continue
        replace_symlink(link_path, os.path.join(OWNERS_DIRNAME, BANK_NAME, package_id))

    for entry in sorted(links_dir.iterdir()):
        if entry.name == OWNERS_DIRNAME or entry.name in package_ids:
            continue
        if owned_by_bank(entry, owner_dir):
            entry.unlink(missing_ok=True)

    return problems


def main() -> int:
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if not plugin_root:
        print("Cannot publish frameworks path: CLAUDE_PLUGIN_ROOT is empty.", file=sys.stderr)
        return 0

    try:
        problems = publish(Path(plugin_root), Path.home() / ".claude")
    except OSError as error:
        print(f"Cannot publish frameworks path: {error}", file=sys.stderr)
        return 0

    for problem in problems:
        print(problem, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
