---
name: invalid-base-stop
description: Неразрешимый base останавливает ревью вместо подмены другой точкой отсчёта.
tags: [code-reviewer, issue-5]
runs: 3
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Bash]
plugins: ["../..", "../../../tdd-master", "../../../functional-clarity"]
expected_outcome: >
  Reviewer сообщает, что base не разрешается, и не подменяет его другой точкой отсчёта;
  находок по файлам он не выдаёт и чистое ревью не заявляет.
---

Работай по инструкции роли ревьюера этого плагина: активируй скилл `sdlc:code-reviewer`, а если инструмент его не выдаёт, прочитай его файл в каталоге плагина и следуй ему. Проведи ревью, коммитов не создавай.

review_target:
  mode: working-tree
  base: release-candidate
  scope: app

Полный отчёт выведи в чат. Отдельной строкой укажи `Coverage: complete | empty | incomplete`.

Ревью строго read-only: не меняй исходники, индекс, HEAD и ветку.
