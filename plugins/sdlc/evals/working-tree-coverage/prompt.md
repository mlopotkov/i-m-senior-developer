---
name: working-tree-coverage
description: Ревью текущего рабочего дерева относительно base охватывает staged, unstaged и untracked в области и не трогает дерево.
tags: [code-reviewer, issue-5]
runs: 3
max_turns: 40
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Bash]
plugins: ["../..", "../../../tdd-master", "../../../functional-clarity"]
expected_outcome: >
  Reviewer охватывает staged, unstaged, совмещённый staged+unstaged, untracked внутри области,
  удаление и обе стороны переименования; не включает untracked и изменения вне области и не
  втягивает в разбор игнорируемый файл; называет Coverage: complete; рабочее дерево остаётся прежним.
---

Работай по инструкции роли ревьюера этого плагина: активируй скилл `sdlc:code-reviewer`, а если инструмент его не выдаёт, прочитай его файл в каталоге плагина и следуй ему. Проведи ревью текущего результата работы, коммитов не создавай.

review_target:
  mode: working-tree
  base: base
  scope: app

Полный отчёт запиши в `review-request-changes/REVIEW-01.md`. В заголовке назови режим, base, область и два списка: просмотренные файлы и исключённые из области. Отдельной строкой укажи `Coverage: complete | empty | incomplete`.

В чат верни только компактную сводку:

```text
Status: clean | changes-requested
Report: review-request-changes/REVIEW-01.md
Coverage: complete | empty | incomplete
Findings: major N; minor N; security N; design N
Blocking: N
Certification boundary: <что статическое ревью не удостоверяет>
Summary: <кратко>
```

Ревью строго read-only: не меняй исходники, индекс, HEAD и ветку. Запись названного review report — единственное разрешённое изменение файлов.
