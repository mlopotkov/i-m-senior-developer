---
name: exact-path-scope
description: Определение exact остаётся при supplied path, а не переносится на отчёт.
tags: [russian-style, issue-7]
runs: 3
max_turns: 6
timeout_seconds: 300
allowed_tools: [Read, Skill]
plugins: ["../.."]
expected_outcome: >
  Формулировка сохраняет референт и наблюдённые факты по канону русского технического стиля.
---

Активируй скилл `clarity-language:russian-style` и переведи требование `write the REVIEW report to the exact supplied path`. Верни только русскую формулировку. Не меняй имя `REVIEW`.
