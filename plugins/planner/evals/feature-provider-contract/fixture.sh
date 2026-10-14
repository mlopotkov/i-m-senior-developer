#!/usr/bin/env bash
set -euo pipefail

mkdir -p .claude features
cat > .claude/planner-context.md <<'CONTEXT'
# Planner context

## §1 Каталог агентов

- `planner:product-baseline` — встроенный ограниченный поставщик продуктовой проработки.

## §5 Пути артефактов

- features: `features/`

## §9 Способности и поставщики

| Способность | Нужна для | Поставщик | Источник | Доступность | Покрытие | Основание | Ограничения | Приоритет |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| problem_outcome_framing | idea, epic, feature | planner:product-baseline | planner plugin | available | partial | plugins/planner/skills/product-baseline/SKILL.md | нет данных о пользователях | builtin |
| decision_dialogue | idea, epic, roadmap, feature | planner:product-baseline | planner plugin | available | partial | plugins/planner/skills/product-baseline/SKILL.md | нет подтверждения гипотезы | builtin |
CONTEXT
