---
name: mined-guards-prose-diff
description: Дифф без исполняемого кода переводит ревью в режим текста — обход уязвимостей пропущен, раздел безопасности остался, файл прочитан целиком.
tags: [code-reviewer, mined-guards]
runs: 3
max_turns: 40
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Bash]
plugins: ["../..", "../../../tdd-master", "../../../functional-clarity"]
expected_outcome: >
  Reviewer switches to documentation mode: no OWASP category walk-through, the Security
  section still present, the planted token still flagged, the redefined term caught by
  reading the whole changed file, and the proposal contrasted against the decision the
  repository already recorded.
---

Работай по инструкции роли ревьюера этого плагина: активируй скилл `sdlc:code-reviewer`, а если инструмент его не выдаёт, прочитай его файл в каталоге плагина и следуй ему. Проведи ревью текущего результата работы, коммитов не создавай.

review_target:
  mode: working-tree
  base: base
  scope: docs

Полный отчёт по шаблону роли запиши в `review-request-changes/REVIEW-01.md`. В чат верни только компактную сводку с полями Status, Report, Coverage, Findings, Blocking, Certification boundary и Summary. Ревью строго read-only: не меняй исходники, индекс, HEAD и ветку. Запись названного review report — единственное разрешённое изменение файлов.
