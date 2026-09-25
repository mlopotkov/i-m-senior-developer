---
name: mined-guards-code-diff
description: Ревью кодового диффа применяет правила о единственном владельце, совместимости договора, тесте мимо механизма и англицизме в переводе.
tags: [code-reviewer, mined-guards]
runs: 3
max_turns: 40
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Bash]
plugins: ["../..", "../../../tdd-master", "../../../functional-clarity"]
expected_outcome: >
  Reviewer flags the re-derived eligibility predicate against the owner named in
  ARCHITECTURE.md, blocks the shared-base rename while not blocking the added optional
  field, names that no test covers the event-driven advance, raises the latin dev term in
  the translated catalogue as advisory without touching the brand name, keeps the second
  module's defect as its own finding, and claims no domain pass it did not run.
---

Работай по инструкции роли ревьюера этого плагина: активируй скилл `sdlc:code-reviewer`, а если инструмент его не выдаёт, прочитай его файл в каталоге плагина и следуй ему. Проведи ревью текущего результата работы, коммитов не создавай.

review_target:
  mode: working-tree
  base: base
  scope: app

Полный отчёт по шаблону роли запиши в `review-request-changes/REVIEW-01.md`. В чат верни только компактную сводку с полями Status, Report, Coverage, Findings, Blocking, Certification boundary и Summary. Ревью строго read-only: не меняй исходники, индекс, HEAD и ветку. Запись названного review report — единственное разрешённое изменение файлов.
