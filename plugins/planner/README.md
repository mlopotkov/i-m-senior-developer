# planner

Claude Code plugin for file-backed product discovery, feature planning, and
implementation orchestration. This file answers how the plugin is structured in
the repository. The contract — what each command takes and returns, the
freshness gate, capability routing, report discipline — lives on
[`docs/plugins/planner.md`](../../docs/plugins/planner.md).

## Structure

```text
plugins/planner/
├── .claude-plugin/
│   └── plugin.json
├── agents/
│   └── planner.md
├── commands/
│   ├── plan-idea.md
│   ├── plan-epic.md
│   ├── plan-roadmap.md
│   ├── plan-feat.md
│   ├── plan-jira.md
│   ├── plan.md
│   ├── plan-do.md
│   ├── plan-do-workflow.md
│   └── plan-reflect.md
├── workflows/
│   └── plan-do-workflow.js
├── skills/
│   ├── planner/
│   │   ├── SKILL.md
│   │   ├── assets/
│   │   │   ├── plan_state.py
│   │   │   ├── work_hint.py
│   │   │   ├── execution_outputs.py
│   │   │   ├── test_plan_state.py
│   │   │   ├── test_work_hint.py
│   │   │   └── test_execution_outputs.py
│   │   └── references/
│   │       ├── bootstrap.md
│   │       ├── architecture-mode.md
│   │       ├── execution-mode.md
│   │       └── template-context.md
│   ├── product-discovery/
│   │   ├── SKILL.md
│   │   ├── assets/
│   │   │   ├── product_state.py
│   │   │   └── test_product_state.py
│   │   └── references/
│   │       ├── routing.md
│   │       ├── dialogue.md
│   │       ├── pov-review.md
│   │       ├── idea-mode.md
│   │       ├── epic-mode.md
│   │       ├── roadmap-mode.md
│   │       └── feature-mode.md
│   ├── product-baseline/
│   │   └── SKILL.md
│   └── planner-reflect/
│       └── SKILL.md
├── hooks/
│   ├── hooks.json
│   ├── product_intake_hint.py
│   ├── test_product_intake_hint.py
│   └── README.md
├── evals/
│   ├── README.md
│   ├── run.py
│   ├── test_run.py
│   ├── idea-routing/
│   ├── multi-step-input/
│   └── baseline-provider-limits/
└── README.md
```

`plan_state.py` imports `work_hint.py`, which imports `execution_outputs.py`, so
the three live in one directory and must be invoked by absolute path from there.
A run also writes `evals/results/<run-id>/` with the aggregate result and an HTML
report; that directory is gitignored and is not part of the repository tree.

## Installation

Add this marketplace to Claude Code and install the plugin:

```text
/plugin marketplace add spumer/i-m-senior-developer
/plugin install planner@i-m-senior-developer
```

## Known limitations

Claude Code может добавить субагенту инструкцию не записывать Markdown-отчёты
даже тогда, когда `/planner:plan-do` выдал ему точный путь. В этом случае
субагент может не вызвать `Write` и оставить обязательный файл пустым. Пустой
файл не считается готовым отчётом; подробнее — в [сообщении о баге Claude Code](https://github.com/anthropics/claude-code/issues/101519).

Есть и отдельный отказ самого `Write` для некоторых имён файлов отчётов:
субагент вызывает инструмент, но тот отклоняет запись. Подходящее имя файла
не устраняет риск отказа субагента вызвать `Write`.

Пользователь наблюдал запись отчёта в новом процессе Claude Code после удаления
этой инструкции через `CLAUDE_CODE_REMOVE_PROMPT_STRINGS`. Для разового запуска
из оболочки:

```bash
export CLAUDE_CODE_REMOVE_PROMPT_STRINGS='["\n- Do NOT Write report/summary/findings/analysis .md files. Return findings directly as your final assistant message — the parent agent reads your text output, not files you create. (Files written as input to another tool are fine; this note is about report files.)"]'
claude
```

Для следующих запусков можно добавить поле `env` в личный
`~/.claude/settings.json` (если файл уже содержит настройки, добавьте только
поле в существующий объект):

```json
{
  "env": {
    "CLAUDE_CODE_REMOVE_PROMPT_STRINGS": "[\"\\n- Do NOT Write report/summary/findings/analysis .md files. Return findings directly as your final assistant message — the parent agent reads your text output, not files you create. (Files written as input to another tool are fine; this note is about report files.)\"]"
  }
}
```

Значение — строка с JSON-массивом из одного точного фрагмента системной
инструкции; `\n` задаёт перенос строки перед дефисом. Выберите один из двух
способов и запустите **новый процесс** Claude Code. Не записывайте переменную
в проектный `.claude/settings.json`: Claude Code игнорирует её там.
Переменная недокументирована, не поддерживается как настройка плагина и не
гарантирует результат в другом окружении. Она не снимает отдельную проверку
имён файлов инструментом `Write`.

## Evaluation

```bash
python3 plugins/planner/evals/run.py
```

The wrapper pins the run contract, verifies the aggregate result, and refuses a
partial run. General rules for plugin testing live in `docs/testing/`; the
numbers of a run stay in its `aggregate-result.json`, which git does not track.
