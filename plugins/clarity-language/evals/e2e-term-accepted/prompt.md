---
name: e2e-term-accepted
description: Допустимый профессиональный термин E2E не исправляется по формальному признаку.
tags: [russian-style, issue-7]
runs: 3
max_turns: 6
timeout_seconds: 300
allowed_tools: [Read, Skill]
plugins: ["../.."]
expected_outcome: >
  Формулировка сохраняет референт и наблюдённые факты по канону русского технического стиля.
---

Активируй скилл `clarity-language:russian-style` и проверь фразу. Если правка не нужна, верни её без изменений и коротко укажи, что ошибка не найдена.

«Проверочный E2E после реализации».
