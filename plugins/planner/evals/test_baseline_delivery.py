import json
from pathlib import Path
import runpy
import tempfile
from typing import Any
import unittest

from baseline_delivery import CASE, SKILL, DeliveryError, validate_delivery

ROOT = "/tmp/eval/home/cwd"
CALL = "toolu_baseline"
ANSWER = (
    '```json\n{"problem": "упорядочено", "outcome": "черновик", '
    '"limitations": ["нет данных о пользователях"]}\n```\n\n'
    "## Ограничения\n\nИсследование не проводилось."
)


def trajectory() -> list[dict[str, Any]]:
    """Наблюдённая форма удачного baseline-повтора: корневой Skill, затем итог."""
    return [
        {"type": "system", "subtype": "init", "cwd": ROOT, "tools": ["Skill", "Write"]},
        {"type": "assistant", "parent_tool_use_id": None, "message": {"content": [
            {"type": "text", "text": "I'll invoke the skill as instructed."}]}},
        {"type": "assistant", "parent_tool_use_id": None, "message": {"content": [
            {"type": "tool_use", "id": CALL, "name": "Skill",
             "input": {"skill": SKILL, "args": "Вид документа: idea. Запись файлов запрещена."}}]}},
        # Наблюдённая форма: удачный результат Skill не несёт поля is_error.
        {"type": "user", "parent_tool_use_id": None, "message": {"content": [
            {"type": "tool_result", "tool_use_id": CALL, "content": "Launching skill: " + SKILL}]},
         "tool_use_result": {"success": True, "commandName": SKILL}},
        {"type": "user", "parent_tool_use_id": None, "message": {"content": [
            {"type": "text", "text": "Base directory for this skill: /workspace/plugins/planner"
                                     "/skills/product-baseline\n\n# Product baseline"}]}},
        {"type": "assistant", "parent_tool_use_id": None, "message": {"content": [
            {"type": "text", "text": ANSWER}]}},
        {"type": "result", "subtype": "success", "is_error": False, "num_turns": 3, "result": ANSWER},
    ]


def block(events, kind):
    for event in events:
        content = event.get("message", {}).get("content", [])
        for candidate in content if isinstance(content, list) else []:
            if candidate.get("type") == kind:
                return candidate
    raise AssertionError("fixture block missing")


def receipt_event(events):
    """Событие, несущее машинную квитанцию запуска скилла."""
    for event in events:
        content = event.get("message", {}).get("content", [])
        if any(candidate.get("type") == "tool_result" for candidate in content if isinstance(candidate, dict)):
            return event
    raise AssertionError("fixture receipt missing")


def denied(events):
    """Отказ в вызове Skill: результат приходит, но помечен ошибкой."""
    block(events, "tool_result")["is_error"] = True
    return events


def unlaunched(events):
    """Наблюдаемая форма неудачи: is_error нет, квитанция говорит success: false."""
    receipt_event(events)["tool_use_result"]["success"] = False
    return events


def write_trace(root: Path, events) -> Path:
    path = root / "out" / "trace.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")
    return path


def attach_traces(result, output_dir, variant):
    """Дополняет фикстуру feature-пути baseline-трассами, не меняя её."""
    feature = runpy.run_path(str(Path(__file__).with_name("test_feature_flow.py")))
    result = feature["attach_traces"](result, output_dir, variant)
    case = next(c for c in result["cases"] if c["name"] == CASE)
    for index, run in enumerate(case["arms"]["with"]):
        events = trajectory()
        if variant == "denied-skill":
            denied(events)
        run["tracePath"] = str(write_trace(output_dir / "baseline-traces" / str(index), events))
    return result


class BaselineDeliveryTests(unittest.TestCase):
    def verify(self, events):
        with tempfile.TemporaryDirectory() as directory:
            return validate_delivery(write_trace(Path(directory), events))

    def test__successful_root_skill_before_answer__accepted(self):
        self.verify(trajectory())

    def test__environment_noise_around_delivery__does_not_hide_it(self):
        events = trajectory()
        events[5:5] = [{"type": "system", "subtype": "thinking_tokens", "count": 416}]
        events.insert(2, {"type": "assistant", "parent_tool_use_id": None, "message": {"content": [
            {"type": "thinking", "thinking": "plan the call"}]}})
        self.verify(events)

    def test__delivery_mutations__refused(self):
        def subagent(events):
            for event in events[2:4]:
                event["parent_tool_use_id"] = "toolu_outer"
            return events

        def answer_first(events):
            events.insert(2, events.pop())
            return events

        mutations = {
            "no-skill-call": lambda e: e[:2] + e[4:],
            "other-skill": lambda e: (block(e, "tool_use")["input"].update(skill="planner:product-discovery"), e)[1],
            "denied-skill": denied,
            "unlaunched-skill": unlaunched,
            "receipt-of-another-skill": lambda e: (receipt_event(e)["tool_use_result"].update(commandName="planner:product-discovery"), e)[1],
            "receipt-without-outcome": lambda e: (receipt_event(e)["tool_use_result"].pop("success"), e)[1],
            "no-receipt": lambda e: (receipt_event(e).pop("tool_use_result"), e)[1],
            # Наблюдённая форма отказавшего инструмента: квитанция приходит текстом.
            "receipt-not-machine-readable": lambda e: (receipt_event(e).update(
                tool_use_result="Error: File does not exist."), e)[1],
            "truncated-skill": lambda e: e[:3] + e[4:],
            "subagent-only-skill": subagent,
            "answer-before-skill": answer_first,
            "empty-answer": lambda e: (e[-1].update(result="  \n"), e)[1],
            "failed-run": lambda e: (e[-1].update(is_error=True), e)[1],
            "answer-not-text": lambda e: (e[-1].update(result=None), e)[1],
            "no-run-result": lambda e: e[:-1],
            "repeated-run-result": lambda e: e + [dict(e[-1])],
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                with self.assertRaises(DeliveryError):
                    self.verify(mutate(trajectory()))

    def test__truncated_carrier__refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.jsonl"
            path.write_text('{"type":"result"')
            with self.assertRaises(DeliveryError):
                validate_delivery(path)

    def test__fixture__carries_both_contracts_of_the_suite(self):
        from feature_flow import validate_trace

        document = {"cases": [
            {"name": CASE, "arms": {"with": [{}, {}]}},
            {"name": "feature-provider-contract", "arms": {"with": [{}, {}]}},
        ]}
        with tempfile.TemporaryDirectory() as directory:
            result = attach_traces(document, Path(directory), "valid")
            baseline, feature = result["cases"]
            for run in baseline["arms"]["with"]:
                validate_delivery(Path(run["tracePath"]))
            for run in feature["arms"]["with"]:
                validate_trace(Path(run["tracePath"]))

            denied_dir = Path(directory) / "denied"
            denied_dir.mkdir()
            refused = attach_traces(document, denied_dir, "denied-skill")
            for run in refused["cases"][0]["arms"]["with"]:
                with self.assertRaises(DeliveryError):
                    validate_delivery(Path(run["tracePath"]))


if __name__ == "__main__":
    unittest.main()
