#!/usr/bin/env python3
"""Страж заголовков навыков по спецификации Agent Skills.

Спецификация (agentskills.io/specification) объявляет закрытый набор
верхнеуровневых полей ``SKILL.md``: ``name``, ``description``, ``license``,
``compatibility``, ``metadata``, ``allowed-tools``. Версия навыка живёт в
``metadata.version``: ``metadata`` — отображение строковых ключей в строковые
значения, любые свои поля клиента кладутся туда. Верхнеуровневое поле вне
набора Claude Code терпит, а клиент, проверяющий заголовок по схеме, вправе
отклонить файл целиком.

Страж разбирает заголовок настоящим YAML-разбором (``yaml.safe_load``), а не
поиском строк: подмена значения на другой тип, вложенность и повтор ключа
должны быть видны так же, как их увидит потребитель заголовка.

Проверяется: рамка ``---`` в начале файла; заголовок — отображение;
верхнеуровневые поля входят в набор спецификации; ``name`` и ``description``
непусты и являются строками; ``name`` совпадает с именем каталога навыка;
``metadata`` — отображение строк в строки.

Успех — код 0 без вывода. Нарушение договора — код 1 с диагностикой. Неверный
корень репозитория — код 64.

Чего страж не удостоверяет: принятие файла другим клиентом. Он воспроизводит
письменную спецификацию, а не поведение конкретного потребителя.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, NoReturn

import yaml

EXIT_OK = 0
EXIT_VIOLATION = 1
EXIT_USAGE = 64

ALLOWED_TOP_LEVEL_FIELDS = frozenset(
    {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
)
REQUIRED_TOP_LEVEL_FIELDS = ("name", "description")
DELIMITER = "---"


class GuardParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(EXIT_USAGE, f"{self.prog}: ошибка: {message}\n")


def read_frontmatter(path: Path) -> tuple[Any, str | None]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as error:
        return None, f"файл навыка не удалось прочитать: {error}"

    lines = text.splitlines()
    if not lines or lines[0].strip() != DELIMITER:
        return None, "рамка заголовка не открыта разделителем «---» в первой строке"

    body: list[str] = []
    for line in lines[1:]:
        if line.strip() == DELIMITER:
            break
        body.append(line)
    else:
        return None, "рамка заголовка не закрыта разделителем «---»"

    try:
        return yaml.safe_load("\n".join(body)), None
    except yaml.YAMLError as error:
        return None, f"заголовок не разбирается как YAML: {error}"


def check_metadata(metadata: Any) -> list[str]:
    if not isinstance(metadata, dict):
        return ["поле «metadata» обязано быть отображением строк в строки"]
    problems = []
    for key, value in metadata.items():
        if not isinstance(key, str):
            problems.append(f"ключ «metadata» не строка: {key!r}")
            continue
        if not isinstance(value, str):
            problems.append(
                f"значение «metadata.{key}» не строка: {value!r}; "
                "число и дата приходят потребителю не строкой, версию писать в кавычках"
            )
    return problems


def check_skill(path: Path, expected_name: str) -> list[str]:
    frontmatter, error = read_frontmatter(path)
    if error is not None:
        return [error]
    if not isinstance(frontmatter, dict):
        return ["заголовок обязан быть отображением полей"]

    problems = []
    unexpected = sorted(str(key) for key in frontmatter if key not in ALLOWED_TOP_LEVEL_FIELDS)
    for key in unexpected:
        hint = ""
        if key == "version":
            hint = "; версия навыка объявляется в «metadata.version»"
        problems.append(f"верхнеуровневое поле «{key}» вне набора спецификации{hint}")

    for field in REQUIRED_TOP_LEVEL_FIELDS:
        value = frontmatter.get(field)
        if not isinstance(value, str) or not value.strip():
            problems.append(f"обязательное поле «{field}» отсутствует или не является непустой строкой")

    declared_name = frontmatter.get("name")
    if isinstance(declared_name, str) and declared_name.strip() != expected_name:
        problems.append(
            f"поле «name» — «{declared_name.strip()}», а каталог навыка — «{expected_name}»"
        )

    if "metadata" in frontmatter:
        problems.extend(check_metadata(frontmatter["metadata"]))

    return problems


def iter_skill_files(root: Path) -> list[Path]:
    return sorted(root.glob("plugins/*/skills/*/SKILL.md"))


def check_skill_frontmatter(root: Path) -> list[str]:
    problems = []
    for path in iter_skill_files(root):
        relative = path.relative_to(root)
        for problem in check_skill(path, path.parent.name):
            problems.append(f"{relative}: {problem}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = GuardParser(description="Проверка заголовков навыков по спецификации Agent Skills.")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="корень репозитория с plugins/ (по умолчанию — родитель scripts/)",
    )
    options = parser.parse_args(argv)
    root = options.root.expanduser()
    if not root.is_dir():
        parser.error(f"нет каталога {root}")
    root = root.resolve()
    if not (root / "plugins").is_dir():
        parser.error(f"нет каталога {root / 'plugins'}")

    problems = check_skill_frontmatter(root)
    for problem in problems:
        print(problem, file=sys.stderr)
    return EXIT_VIOLATION if problems else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
