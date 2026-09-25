---
name: consumed-draft-collocation
description: Механический перевод consumed для файла заменяется фактическим действием.
tags: [russian-style, issue-7]
runs: 3
max_turns: 6
timeout_seconds: 300
allowed_tools: [Read, Skill]
plugins: ["../.."]
expected_outcome: >
  Формулировка сохраняет референт и наблюдённые факты по канону русского технического стиля.
---

Активируй скилл `clarity-language:russian-style` и отредактируй фразу для технического отчёта. Верни только итоговую формулировку.

Исходная фраза: «Черновик потреблён и удалён».
Наблюдаемый факт: `check-response --consume` проверил JSON и удалил временный файл.
