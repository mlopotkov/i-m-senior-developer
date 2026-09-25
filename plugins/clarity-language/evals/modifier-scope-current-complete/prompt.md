---
name: modifier-scope-current-complete
description: Определения current и complete остаются при исходных объектах.
tags: [russian-style, issue-7]
runs: 3
max_turns: 6
timeout_seconds: 300
allowed_tools: [Read, Skill]
plugins: ["../.."]
expected_outcome: >
  Формулировка сохраняет референт и наблюдённые факты по канону русского технического стиля.
---

Активируй скилл `clarity-language:russian-style` и переведи требование: `Review the current working tree and report complete file coverage.` Верни только русскую формулировку.
