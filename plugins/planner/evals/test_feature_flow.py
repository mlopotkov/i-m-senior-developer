import copy
import json
import subprocess
import shlex
from pathlib import Path
import tempfile
import unittest
from typing import Any

from feature_flow import FlowError, validate_trace

HELPER = "python3 /plugin/product_state.py "
ROOT = "/tmp/eval/home/cwd"
LEASE = "/tmp/eval/tmp/provider-response.json"
README = ROOT + "/features/FEAT-0001-provider-response-contract/README.md"
CONTRACT = {"for": "feature", "fields": {
    "problem": {"required": True, "type": "text"},
    "outcome": {"required": True, "type": "text"},
    "limitations": {"required": True, "type": "list[text]"},
}}
DRAFT = {"problem": "problem", "outcome": "outcome", "limitations": ["limited"]}


def trajectory() -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = [{"type": "system", "subtype": "init", "cwd": ROOT}]

    def tool(name, arguments, response):
        identifier = "call-" + str(len(events))
        events.append({"type": "assistant", "parent_tool_use_id": None, "message": {
            "content": [{"type": "tool_use", "id": identifier, "name": name, "input": arguments}]
        }})
        events.append({"type": "user", "parent_tool_use_id": None, "message": {
            "content": [{"type": "tool_result", "tool_use_id": identifier,
                         "is_error": False, "content": json.dumps(response)}]
        }})

    def helper(command, response):
        tool("Bash", {"command": HELPER + command}, response)

    helper("route .claude/planner-context.md --for feature --pin planner:product-baseline", {
        "for": "feature", "writer": "planner", "candidates": [{
            "selected": True, "provider": "planner:product-baseline"
        }],
    })
    helper("response-contract --for feature", CONTRACT)
    helper("reserve-response-draft", {"path": LEASE})
    tool("Agent", {"subagent_type": "planner:product-baseline", "prompt": json.dumps(CONTRACT)}, DRAFT)
    tool("Write", {"file_path": LEASE, "content": json.dumps(DRAFT)}, "File created")
    helper(f"check-response {LEASE} --for feature --consume", {
        "accepted": True, "for": "feature", "draft_removed": True, "path": LEASE,
    })
    helper("allocate feature --root features --slug provider-response-contract", {
        "created": True, "kind": "feature", "path": str(Path(README).parent),
    })
    helper(f"validate-target feature {README} --directory {Path(README).parent}", {
        "kind": "feature", "status": "current", "path": README,
    })
    tool("Write", {"file_path": README + ".prepared", "content": "# Requirements"}, "File created")
    helper(f"sync feature {README} --body-file {README}.prepared --semantic-change yes --analysis-by planner:product-baseline --readiness ready", {
        "plan_type": "feature", "status": "current", "path": README,
        "version": 1, "content_sha256": "a" * 64,
    })
    return events


def attach_traces(result, output_dir, variant):
    case = next(c for c in result["cases"] if c["name"] == "feature-provider-contract")
    for index, run in enumerate(case["arms"]["with"]):
        root = output_dir / "fixture-traces" / str(index)
        events = trajectory()
        if variant == "changed-response":
            call(events, "Write", "provider-response")["input"]["content"] = json.dumps({**DRAFT, "problem": "altered"})
        text = "\n".join(json.dumps(event) for event in events).replace("/tmp/eval", str(root))
        helper = str(Path(__file__).resolve().parents[1] / "skills/product-discovery/assets/product_state.py")
        text = text.replace("/plugin/product_state.py", helper if variant != "fake-helper" else "/fake/product_state.py")
        path = root / "out" / "trace.jsonl"
        path.parent.mkdir(parents=True)
        path.write_text(text + "\n")
        run["tracePath"] = str(path)
    return result


def edit_events(identifier, file_path, name):
    return [
        {"type": "assistant", "parent_tool_use_id": None, "message": {"content": [{
            "type": "tool_use", "id": identifier, "name": name,
            "input": {"file_path": file_path, "old_string": "# Requirements",
                      "new_string": "# Requirements\n\n## Problem"},
        }]}},
        {"type": "user", "parent_tool_use_id": None, "message": {"content": [{
            "type": "tool_result", "tool_use_id": identifier, "is_error": False, "content": "edited",
        }]}},
    ]


def position(events, block):
    for index, event in enumerate(events):
        if block in event.get("message", {}).get("content", []):
            return index
    raise AssertionError("fixture block missing")


def with_edit(events, file_path, where, name="Edit"):
    anchors = {
        "before-prepared": lambda: position(events, call(events, "Write", ".prepared")),
        "before-sync": lambda: position(events, call(events, "Bash", "sync feature")),
        "after-sync": lambda: len(events),
    }
    at = anchors[where]()
    events[at:at] = edit_events(f"{name}-{where}-{len(events)}", file_path, name)
    return events


def call(events, name, word=None):
    for event in events:
        for block in event.get("message", {}).get("content", []):
            if block.get("type") == "tool_use" and block["name"] == name:
                if word is None or word in json.dumps(block["input"]):
                    return block
    raise AssertionError("fixture call missing")


def response(events, identifier):
    for event in events:
        for block in event.get("message", {}).get("content", []):
            if block.get("type") == "tool_result" and block["tool_use_id"] == identifier:
                return block
    raise AssertionError("fixture response missing")


class FeatureFlowTests(unittest.TestCase):
    def test__provider_configuration__preloads_method_without_write_permission(self):
        import yaml
        agent = Path(__file__).resolve().parents[1] / "agents/product-baseline.md"
        fields = yaml.safe_load(agent.read_text().split("---", 2)[1])
        self.assertEqual(fields.get("skills"), ["planner:product-baseline"])
        self.assertNotIn("Write", fields["tools"])

    def test__kind_grader__rejects_unrelated_agent_with_matching_words(self):
        import yaml
        path = Path(__file__).parent / "feature-provider-contract/graders/passes-machine-contract-kind.md"
        fields = yaml.safe_load(path.read_text().split("---", 2)[1])
        inputs = [
            {"subagent_type": "planner:product-baseline", "prompt": json.dumps(CONTRACT)},
            {"subagent_type": "general-purpose", "prompt": "Check Bash for feature evaluation"},
            {"subagent_type": "planner:product-baseline", "prompt": json.dumps({**CONTRACT, "for": "idea"})},
        ]
        result = subprocess.run(["node", "-e",
            "const re=new RegExp(process.argv[1]); const values=JSON.parse(process.argv[2]); console.log(JSON.stringify(values.map(x=>re.test(JSON.stringify(x)))));",
            fields["input_match"], json.dumps(inputs)], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout), [True, False, False])

    def verify(self, events):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.jsonl"
            path.write_text("\n".join(json.dumps(event) for event in events) + "\n")
            return validate_trace(path)

    def test__complete_actual_tool_trajectory__accepted_despite_shell_warnings(self):
        events = trajectory()
        route = call(events, "Bash", " route ")
        result = response(events, route["id"])
        result["content"] = "/bin/bash: profile unavailable\n" + result["content"]
        events.insert(1, {"type": "system", "message": "informational event"})
        self.verify(events)

    def test__claims_without_tools__cannot_replace_observed_steps(self):
        events = [{"type": "system", "subtype": "init", "cwd": ROOT}, {
            "type": "assistant", "message": {"content": [{"type": "text", "text":
                "route response-contract reserve-response-draft planner:product-baseline check-response --consume sync all succeeded"}]}
        }]
        with self.assertRaises(FlowError):
            self.verify(events)

    def test__machine_contract_mutations__refused(self):
        mutations = {
            "invalid-input": lambda e: call(e, "Bash", " route ").update(input=None),
            "invalid-shell-command": lambda e: call(e, "Bash", " route ")["input"].update(command=HELPER + "route 'unfinished"),
            "wrong-provider": lambda e: call(e, "Agent")["input"].update(subagent_type="general-purpose"),
            "wrong-contract": lambda e: call(e, "Agent")["input"].update(prompt=json.dumps({**CONTRACT, "for": "idea"})),
            "wrong-response-path": lambda e: call(e, "Write", "provider-response")["input"].update(file_path=ROOT + "/response.json"),
            "different-provider-body": lambda e: call(e, "Write", "provider-response")["input"].update(content=json.dumps({**DRAFT, "problem": "changed"})),
            "failed-route": lambda e: response(e, call(e, "Bash", " route ")["id"]).update(is_error=True),
            "no-consume": lambda e: call(e, "Bash", "check-response")["input"].update(command=HELPER + "check-response " + LEASE + " --for feature"),
            "not-accepted": lambda e: response(e, call(e, "Bash", "check-response")["id"]).update(content=json.dumps({"accepted": False})),
            "direct-README-write": lambda e: call(e, "Write", ".prepared")["input"].update(file_path=README),
            "bad-final-state": lambda e: response(e, call(e, "Bash", "sync feature")["id"]).update(content=json.dumps({"status": "stale"})),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                events = trajectory()
                mutate(events)
                with self.assertRaises(FlowError):
                    self.verify(events)

    def test__provider_json_copy_outside_lease__refused(self):
        events = trajectory()
        events[11:11] = [
            {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "copy", "name": "Write", "input": {"file_path": ROOT + "/extra.json", "content": json.dumps(DRAFT)}}]}},
            {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "copy", "is_error": False, "content": "copied"}]}},
        ]
        with self.assertRaises(FlowError):
            self.verify(events)

    def test__shell_mutations_of_lease_or_canonical_file__refused(self):
        altered = {**DRAFT, "limitations": ["changed by shell"]}
        commands = [
            f"printf '%s' {shlex.quote(json.dumps(altered))} >{LEASE}",
            f"printf bad >>{README}",
            f"echo ok\nprintf bad >{README}",
            f"echo $(printf bad >{README})",
            f"echo ok | tee {README}",
            "/tmp/fake/echo ignored",
        ]
        for command in commands:
            with self.subTest(command=command):
                events = trajectory()
                events[11:11] = [
                    {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "mutation", "name": "Bash", "input": {"command": command}}]}},
                    {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "mutation", "is_error": False, "content": ""}]}},
                ]
                with self.assertRaises(FlowError):
                    self.verify(events)
        events = trajectory()
        call(events, "Bash", "sync feature")["input"]["command"] += f"; printf bad >{README}"
        with self.assertRaises(FlowError):
            self.verify(events)

    def test__unexpected_writer_or_edit__refused(self):
        for name, arguments in (
            ("Write", {"file_path": ROOT + "/program.py", "content": "side effect"}),
            ("Edit", {"file_path": LEASE, "old_string": "limited", "new_string": "changed"}),
        ):
            with self.subTest(name=name):
                events = trajectory()
                events.extend([
                    {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "unexpected", "name": name, "input": arguments}]}},
                    {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "unexpected", "is_error": False, "content": "changed"}]}},
                ])
                with self.assertRaises(FlowError):
                    self.verify(events)

    def test__prepared_body_edited_before_sync__accepted(self):
        events = with_edit(trajectory(), README + ".prepared", "before-sync")
        with_edit(events, README + ".prepared", "before-sync")
        self.verify(events)

    def test__editing_outside_prepared_window__refused(self):
        cases = {
            "lease": (LEASE, "before-sync", "Edit"),
            "canonical": (README, "before-sync", "Edit"),
            "unrelated-file": (ROOT + "/notes.md", "before-sync", "Edit"),
            "prepared-before-write": (README + ".prepared", "before-prepared", "Edit"),
            "prepared-after-sync": (README + ".prepared", "after-sync", "Edit"),
            "notebook-on-prepared": (README + ".prepared", "before-sync", "NotebookEdit"),
        }
        for name, (path, where, tool) in cases.items():
            with self.subTest(name=name):
                events = with_edit(trajectory(), path, where, tool)
                with self.assertRaises(FlowError):
                    self.verify(events)

    def test__manual_echo_contract_after_failed_helper__refused(self):
        for separator in (";", "||"):
            with self.subTest(separator=separator):
                events = trajectory()
                command = HELPER + "response-contract --for invalid " + separator + " echo " + shlex.quote(json.dumps(CONTRACT))
                call(events, "Bash", "response-contract")["input"]["command"] = command
                with self.assertRaises(FlowError):
                    self.verify(events)

    def test__second_check_or_cleanup_after_write__refused(self):
        for command in (f"check-response {LEASE} --for feature --consume",
                        f"release-response-draft {LEASE}"):
            with self.subTest(command=command):
                events = trajectory()
                events.extend([
                    {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "extra", "name": "Bash", "input": {"command": HELPER + command}}]}},
                    {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "extra", "content": "{}", "is_error": False}]}},
                ])
                with self.assertRaises(FlowError):
                    self.verify(events)

    def test__missing_route_result_or_wrong_step_order__refused(self):
        events = trajectory()
        route_id = call(events, "Bash", " route ")["id"]
        missing = [event for event in events if not any(
            block.get("tool_use_id") == route_id
            for block in event.get("message", {}).get("content", [])
        )]
        wrong_order = copy.deepcopy(events)
        wrong_order[1:5] = wrong_order[3:5] + wrong_order[1:3]
        for candidate in (missing, wrong_order):
            with self.assertRaises(FlowError):
                self.verify(candidate)

    def test__truncated_carrier__refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.jsonl"
            path.write_text('{"type":"assistant"')
            with self.assertRaises(FlowError):
                validate_trace(path)


if __name__ == "__main__":
    unittest.main()
