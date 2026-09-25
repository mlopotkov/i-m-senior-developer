---
name: mined-guards-architect
description: Архитектура на стеке без справочника берёт единицу границы из самого стека, покрывает каждый критерий приёмки и выпускает проверяемый запрет импорта.
tags: [architect, mined-guards]
runs: 3
max_turns: 60
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep, Skill, Write]
append_system_prompt: >
  Первым действием обязательно активируй Skill sdlc:architect. Не отвечай и не
  начинай анализ, пока договор роли не загружен; если Skill недоступен, прочитай
  файл скилла из каталога плагина. Первичный результат — названный файл
  архитектуры: запиши его до итогового сообщения.
plugins: ["../..", "../../../tdd-master", "../../../functional-clarity"]
expected_outcome: >
  The architecture document traces every acceptance criterion to a context, takes its
  bounded-context seam from the detected stack instead of a Django app or a React feature
  folder, and states a forbidden-import invariant separating the pure turn logic from the
  framework scene.
---

Работай по инструкции роли архитектора этого плагина: активируй скилл `sdlc:architect`, а если инструмент его не выдаёт, прочитай его файл в каталоге плагина и следуй ему.

Построй архитектуру по требованиям `features/FEAT-0001-turn-timer/README.md` и запиши её в `features/FEAT-0001-turn-timer/ARCH-01.md`. Файл — первичный результат: после загрузки инструкции сначала запиши в него шапку и каркас всех обязательных разделов, затем наполняй. Не оставляй документ только в чате. После записи верни в чат только путь, статус и краткую сводку — полный документ второй раз не печатай.
