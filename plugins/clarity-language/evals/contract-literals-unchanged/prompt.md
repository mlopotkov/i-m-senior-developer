---
name: contract-literals-unchanged
description: Команды, имена полей и идентификаторы не переводятся.
tags: [russian-style, issue-7]
runs: 3
max_turns: 6
timeout_seconds: 300
allowed_tools: [Read, Skill]
plugins: ["../.."]
expected_outcome: >
  Формулировка сохраняет референт и наблюдённые факты по канону русского технического стиля.
---

Активируй скилл `clarity-language:russian-style` и сделай фразу естественной, сохранив контрактные литералы без изменений. Верни только итоговую формулировку.

«После check-response проверь scope_in и сохрани значение feature_id».
