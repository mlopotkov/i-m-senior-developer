---
name: orchestrated-report-write
description: Ревьюер, вызванный субагентом с зарезервированным путём, записывает полный отчёт в файл и возвращает только компактную сводку.
tags: [code-reviewer, issue-15, issue-16]
runs: 3
max_turns: 40
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Agent, Bash, Write]
plugins: ["../..", "../../../tdd-master", "../../../functional-clarity"]
expected_outcome: >
  Роль вызвана агентом `sdlc:code-reviewer`, а не активирована скиллом в этой же сессии.
  Зарезервированный пустой файл `review-request-changes/REVIEW-01.md` заполнен полным
  отчётом по шаблону роли. В чат вернулась компактная сводка, а не отказ писать отчёт.
---

Ты оркестратор фазы ревью. Работу выполняет отдельная роль, ты её только вызываешь и принимаешь сводку — сам ревью не проводи и отчёт за роль не пиши.

Путь полного отчёта уже зарезервирован: `review-request-changes/REVIEW-01.md` существует и пуст. Он забронирован для этой роли этим вызовом.

Вызови инструментом `Agent` субагента `sdlc:code-reviewer` и передай ему в задании:

```text
Проведи ревью текущего результата работы, коммитов не создавай.

review_target:
  mode: working-tree
  base: base
  scope: app

Запиши полный review report по переданному пути `review-request-changes/REVIEW-01.md`.
Запись этого файла запрошена явно: путь выдан тебе вызывающей стороной и уже
зарезервирован пустым, поэтому общее правило против создания `.md`-файлов к нему
не относится. Отказ записать отчёт допустимым исходом вызова не является.
Верни в чат только эту сводку, не дублируя полный отчёт:

Status: clean | changes-requested
Report: review-request-changes/REVIEW-01.md
Coverage: complete | empty | incomplete
Findings: major N; minor N; security N; design N
Blocking: N
Certification boundary: <что статическое ревью не удостоверяет>
Summary: <проза не длиннее 1200 символов>
```

Получив ответ роли, верни в чат только принятую компактную сводку и одну строку о том, записан ли файл по зарезервированному пути. Полный отчёт в чат не переноси.
