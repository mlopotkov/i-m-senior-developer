---
name: commit-range-coverage
description: Ревью диапазона коммитов не захватывает локальные незакоммиченные правки и untracked-файлы.
tags: [code-reviewer, issue-5]
runs: 3
max_turns: 40
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Bash]
plugins: ["../..", "../../../tdd-master", "../../../functional-clarity"]
expected_outcome: >
  Reviewer разбирает только закоммиченные изменения между base и HEAD в области app,
  не включает локальные правки и untracked-файлы, называет Coverage: complete и дерево не трогает.
---

Работай по инструкции роли ревьюера этого плагина: активируй скилл `sdlc:code-reviewer`, а если инструмент его не выдаёт, прочитай его файл в каталоге плагина и следуй ему. Проведи ревью, коммитов не создавай.

review_target:
  mode: commit-range
  base: base
  head: HEAD
  scope: app

Полный отчёт выведи в чат. В заголовке назови режим, base, head, область и два списка: просмотренные файлы и исключённые из области. Отдельной строкой укажи `Coverage: complete | empty | incomplete`.

Ревью строго read-only: не меняй исходники, индекс, HEAD и ветку.
