---
name: mined-guards-implementer
description: Реализация разбирает вложенные данные со счётом скобок и сдаёт отчёт с разделом рисков, отличным от допущений.
tags: [code-implementer, mined-guards]
runs: 3
max_turns: 60
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Edit, Write, Bash, Skill]
plugins: ["../..", "../../../tdd-master", "../../../functional-clarity"]
expected_outcome: >
  The extractor matches brackets by depth and respects quoting rather than using a flat
  character class, its tests cover a nested group and a bracket inside a string, and the
  implementation report carries a Risks & boundary cases section distinct from Assumptions.
---

Работай по инструкции роли реализатора этого плагина: активируй скилл `sdlc:code-implementer`, а если инструмент его не выдаёт, прочитай его файл в каталоге плагина и следуй ему.

Реализуй `app/extract.py` по архитектуре `features/FEAT-0002-tag-extractor/ARCH-01.md`. Коммитов не создавай. Отчёт о реализации выведи в чат по шаблону роли.
