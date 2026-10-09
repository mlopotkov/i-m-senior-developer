"""Доставка встроенного поставщика по событиям трассы, без судьи.

Граница модуля узкая: он доказывает только успешную доставку и её порядок —
корневой вызов `Skill` со скиллом поставщика завершился успехом раньше, чем
прогон вернул непустой итог. Содержание ответа модуль не читает: правдивость
и названные ограничения остаются работой судьи по итоговому сообщению.
"""

import json
from pathlib import Path

from feature_flow import FlowError, load_calls

CASE = "baseline-provider-limits"
SKILL = "planner:product-baseline"


class DeliveryError(RuntimeError):
    pass


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise DeliveryError(reason)


def read_events(path: Path) -> list:
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    except (OSError, ValueError) as error:
        raise DeliveryError(f"full trace unavailable or malformed: {path}") from error


def launch_receipts(events) -> dict:
    """Машинные квитанции запуска по `tool_use_id` корневых результатов.

    Квитанция лежит на событии, а не в блоке результата, поэтому она
    приписывается вызову только когда событие несёт ровно один результат:
    иначе принадлежность неизвестна и доставка считается недоказанной.
    """
    found = {}
    for event in events:
        if not isinstance(event, dict) or event.get("parent_tool_use_id") is not None:
            continue
        message = event.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        results = [
            block for block in (content if isinstance(content, list) else [])
            if isinstance(block, dict) and block.get("type") == "tool_result"
        ]
        if len(results) == 1:
            found[results[0].get("tool_use_id")] = event.get("tool_use_result")
    return found


def launched(receipt) -> bool:
    """Квитанция подтверждает запуск именно этого скилла."""
    return isinstance(receipt, dict) and receipt.get("success") is True and receipt.get("commandName") == SKILL


def answer_index(events) -> int:
    """Позиция единственного успешного итога корневого прогона."""
    results = [
        (index, event)
        for index, event in enumerate(events)
        if isinstance(event, dict) and event.get("type") == "result" and event.get("parent_tool_use_id") is None
    ]
    require(len(results) == 1, "root run result is missing or repeated")
    index, result = results[0]
    require(result.get("is_error") is False, "root run result reports an error")
    answer = result.get("result")
    require(isinstance(answer, str) and bool(answer.strip()), "root run result carries no answer")
    return index


def validate_delivery(path: Path) -> None:
    events = read_events(path)
    index = answer_index(events)
    receipts = launch_receipts(events)
    try:
        _, calls = load_calls(path)
    except FlowError as error:
        raise DeliveryError(str(error)) from error
    skills = [call for call in calls if call.name == "Skill" and call.arguments.get("skill") == SKILL]
    require(bool(skills), f"no root Skill call for {SKILL}")
    completed = [call for call in skills if call.end >= 0 and not call.failed]
    require(bool(completed), f"root Skill call for {SKILL} did not complete successfully")
    started = [call for call in completed if launched(receipts.get(call.identifier))]
    require(bool(started), f"no machine receipt of a launched {SKILL}")
    require(any(call.end < index for call in started), f"{SKILL} completed only after the answer")


def validate_baseline_runs(document, output_dir: Path) -> None:
    case = next((case for case in document["cases"] if case["name"] == CASE), None)
    if case is None:
        raise DeliveryError("baseline provider case missing")
    checked = []
    for index, run in enumerate(case["arms"]["with"], 1):
        trace = run.get("tracePath")
        if not isinstance(trace, str):
            raise DeliveryError("full baseline trace path missing")
        path = Path(trace)
        require(path.is_absolute() and path.name == "trace.jsonl" and path.parent.name == "out" and not path.is_symlink(), "invalid full trace carrier")
        try:
            validate_delivery(path)
        except DeliveryError as error:
            raise DeliveryError(f"baseline repeat {index}: {error}") from error
        checked.append({"repeat": index, "trace": trace})
    (output_dir / "baseline-delivery.json").write_text(json.dumps({"case": CASE, "validated": checked}, indent=2) + "\n", encoding="utf-8")
