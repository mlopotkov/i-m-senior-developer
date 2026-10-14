"""Полный машинный договор feature-пути по событиям инструментов, без судьи."""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shlex

TARGET = "features/FEAT-0001-provider-response-contract/README.md"
PROVIDER = "planner:product-baseline"


class FlowError(RuntimeError):
    pass


@dataclass
class Call:
    identifier: str
    name: str
    arguments: dict
    start: int
    end: int = -1
    text: str = ""
    failed: bool = False


@dataclass
class Step:
    call: Call
    kind: str
    arguments: list[str]
    value: dict
    part: int


def text_content(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(block.get("text", "") for block in content if isinstance(block, dict))
    raise FlowError("tool result has no text carrier")


def objects(text: str) -> list[dict]:
    decoder = json.JSONDecoder()
    found, position = [], 0
    while position < len(text):
        position = text.find("{", position)
        if position < 0:
            break
        try:
            value, end = decoder.raw_decode(text[position:])
        except ValueError:
            position += 1
            continue
        if isinstance(value, dict):
            found.append(value)
        position += end
    return found


def load_calls(path: Path) -> tuple[str, list[Call]]:
    calls, cwd = {}, None
    try:
        events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    except (OSError, ValueError) as error:
        raise FlowError(f"full trace unavailable or malformed: {path}") from error
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            raise FlowError("trace event must be an object")
        if event.get("parent_tool_use_id") is not None:
            continue
        if cwd is None and event.get("subtype") == "init":
            cwd = event.get("cwd")
        message = event.get("message", {})
        if not isinstance(message, dict) or not isinstance(message.get("content", []), list):
            continue
        for block in message.get("content", []):
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                identifier = block.get("id")
                if not isinstance(identifier, str) or identifier in calls:
                    raise FlowError("missing or repeated tool call identity")
                arguments = block.get("input")
                if not isinstance(arguments, dict) or not isinstance(block.get("name"), str):
                    raise FlowError("tool input or name is malformed")
                calls[identifier] = Call(identifier, block["name"], arguments, index)
            elif block.get("type") == "tool_result" and block.get("tool_use_id") in calls:
                call = calls[block["tool_use_id"]]
                if call.end != -1:
                    raise FlowError("repeated tool result")
                call.end, call.failed = index, block.get("is_error") is True
                call.text = text_content(block.get("content", ""))
    if not isinstance(cwd, str) or not Path(cwd).is_absolute():
        raise FlowError("root trace has no absolute working directory")
    return cwd, list(calls.values())


def strip_redirections(segment: list[str]) -> list[str]:
    result, position = [], 0
    while position < len(segment):
        token = segment[position]
        if token in ("<", ">", ">>", ">&"):
            require(position + 1 < len(segment), "incomplete shell redirection")
            destination = segment[position + 1]
            allowed = destination in ("1", "2") if token == ">&" else destination == "/dev/null"
            require(allowed, "shell file redirection bypasses writer boundary")
            if result and result[-1].isdigit():
                result.pop()
            position += 2
        else:
            require(not any(c in token for c in ("<", ">")) or " " in token, "unsupported shell redirection")
            result.append(token)
            position += 1
    return result


def readonly_segment(segment, cwd):
    require(bool(segment), "empty shell segment")
    name = Path(segment[0]).name
    require(segment[0] in (name, "/bin/" + name, "/usr/bin/" + name), "untrusted shell probe executable")
    if name in ("ls", "pwd", "echo", "true", "false"):
        return
    if name == "printf":
        require("-v" not in segment[1:], "printf assignment is not a read-only probe")
        return
    if name == "cd":
        require(len(segment) == 2 and cwd is not None and absolute(segment[1], cwd) == cwd, "shell changed evaluation root")
        return
    if name == "mkdir":
        require(cwd is not None, "directory scope is unknown")
        destinations = [s for s in segment[1:] if s != "-p"]
        allowed = {absolute("features", cwd), str(Path(absolute(TARGET, cwd)).parent)}
        require(bool(destinations) and all(absolute(s, cwd) in allowed for s in destinations), "mkdir outside selected feature directory")
        return
    raise FlowError("unsupported shell operation outside helper")


def requests(command: str, cwd=None, helper_path: Path | None = None) -> list[list[str]]:
    require(isinstance(command, str), "Bash command must be text")
    command = command.replace("\\\n", " ")
    require("\n" not in command and "$((" not in command and "$(" not in command and "`" not in command, "unsupported multiline or substituted shell operation")
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|<>")
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError as error:
        raise FlowError("Bash command cannot be parsed") from error
    require(not any(token in ("|", "&") for token in tokens), "shell pipeline/background execution is not an observed helper flow")
    segments, current = [], []
    for token in tokens:
        if token and set(token) <= set(";&|"):
            segments.append(current)
            current = []
        else:
            current.append(token)
    segments.append(current)
    found, probes = [], []
    for raw_segment in segments:
        if not raw_segment:
            continue
        segment = strip_redirections(raw_segment)
        indices = [i for i, token in enumerate(segment) if Path(token).name == "product_state.py"]
        if not indices:
            readonly_segment(segment, cwd)
            probes.append(segment)
            continue
        python = segment[0]
        trusted_python = re.fullmatch(r"(?:/(?:usr/bin|usr/local/bin|opt/homebrew/bin)/)?python3(?:\.\d+)?", python)
        if indices != [1] or trusted_python is None:
            raise FlowError("helper must be executed as trusted Python, not merely mentioned")
        if helper_path is not None:
            if cwd is None:
                raise FlowError("helper source has no evaluation root")
            require(Path(absolute(segment[1], cwd)).resolve() == helper_path.resolve(), "unexpected helper source")
        arguments = segment[2:]
        if arguments[-2:] == ["<", "/dev/null"]:
            arguments = arguments[:-2]
        if not arguments:
            raise FlowError("helper command has no operation")
        found.append(arguments)
    if found:
        require("||" not in tokens, "helper fallback cannot prove successful execution")
        require(not any(any(char in " ".join(probe) for char in "{}") for probe in probes), "probe must not impersonate helper JSON")
    return found


def helper_steps(calls: list[Call], cwd: str, helper_path: Path | None = None) -> list[Step]:
    steps = []
    for call in calls:
        if call.name != "Bash":
            continue
        command = call.arguments.get("command", "")
        requested = requests(command, cwd, helper_path)
        if not requested:
            continue
        if call.failed or call.end < 0:
            raise FlowError("helper call did not complete successfully")
        payloads = objects(call.text)
        if len(payloads) != len(requested):
            raise FlowError("helper output is not the complete machine carrier")
        steps.extend(Step(call, args[0], args, value, i)
                     for i, (args, value) in enumerate(zip(requested, payloads)))
    return steps


def absolute(value: str, cwd: str) -> str:
    path = Path(value)
    return os.path.normpath(str(path if path.is_absolute() else Path(cwd) / path))


def before(first, second) -> bool:
    a = first.call if isinstance(first, Step) else first
    b = second.call if isinstance(second, Step) else second
    if a.identifier == b.identifier:
        return isinstance(first, Step) and isinstance(second, Step) and first.part < second.part
    return a.end >= 0 and a.end < b.start


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise FlowError(reason)


def first_step(steps, kind):
    candidates = [step for step in steps if step.kind == kind]
    require(bool(candidates), f"missing observed {kind}")
    return candidates[0]


def provider_input(steps, calls):
    route = first_step(steps, "route")
    contract = first_step(steps, "response-contract")
    lease = first_step(steps, "reserve-response-draft")
    require(route.value.get("for") == "feature" and route.value.get("writer") == "planner", "route kind/writer invalid")
    selected = [row for row in route.value.get("candidates", []) if row.get("selected") is True]
    require(bool(selected) and all(row.get("provider") == PROVIDER for row in selected), "route did not select baseline")
    require(contract.value.get("for") == "feature" and isinstance(contract.value.get("fields"), dict), "feature response contract missing")
    lease_path = lease.value.get("path")
    require(isinstance(lease_path, str) and Path(lease_path).is_absolute(), "lease path missing")
    providers = [call for call in calls if call.name in ("Agent", "Task") and call.arguments.get("subagent_type") == PROVIDER]
    require(len(providers) == 1, "expected one actual baseline invocation")
    provider = providers[0]
    require(provider.end >= 0 and not provider.failed, "provider did not complete")
    require(contract.value in objects(provider.arguments.get("prompt", "")), "provider did not receive actual machine contract")
    drafts = [value for value in objects(provider.text) if all(key in value for key in ("problem", "outcome", "limitations"))]
    require(len(drafts) == 1, "provider did not return one JSON draft")
    return route, contract, lease, provider, lease_path, drafts[0]


def written_response(calls, cwd, lease_path, draft):
    writes = [call for call in calls if call.name == "Write"]
    json_writes = [call for call in writes if absolute(call.arguments.get("file_path", ""), cwd) == lease_path]
    require(bool(json_writes), "JSON was not written to DraftLease.path")
    for write in json_writes:
        require(write.end >= 0 and not write.failed, "JSON write failed")
        try:
            value = json.loads(write.arguments.get("content", ""))
        except ValueError as error:
            raise FlowError("lease write is not JSON") from error
        require(value == draft, "lease JSON differs from provider answer")
    for write in writes:
        if absolute(write.arguments.get("file_path", ""), cwd) == lease_path:
            continue
        try:
            value = json.loads(write.arguments.get("content", ""))
        except ValueError:
            continue
        require(value != draft, "provider JSON copied outside lease")
    return json_writes[-1]


def consumed_response(steps, lease_path, response_write):
    checks = [step for step in steps if step.kind == "check-response"]
    require(len(checks) == 1, "expected exactly one check-response")
    check = checks[0]
    require("--consume" in check.arguments and check.value.get("for") == "feature" and check.value.get("accepted") is True and check.value.get("draft_removed") is True, "response was not accepted and consumed")
    require(check.value.get("path") == lease_path and lease_path in check.arguments, "check consumed a different lease")
    for step in steps:
        if step.kind == "release-response-draft" and lease_path in step.arguments:
            require(step.call.start < response_write.start, "cleanup called after JSON write")
    return check


def synchronized_target(steps, calls, cwd):
    writes = [call for call in calls if call.name == "Write"]
    target = absolute(TARGET, cwd)
    require(not any(absolute(w.arguments.get("file_path", ""), cwd) == target for w in writes), "canonical README written directly")
    require(not any(call.name == "NotebookEdit" for call in calls), "unexpected editing tool bypasses writer boundary")
    allocation = first_step(steps, "allocate")
    validation = first_step(steps, "validate-target")
    sync = first_step(steps, "sync")
    prepared = [w for w in writes if absolute(w.arguments.get("file_path", ""), cwd) == target + ".prepared"]
    require(len(prepared) == 1 and prepared[0].end >= 0 and not prepared[0].failed, "prepared body missing or failed")
    for edit in [call for call in calls if call.name == "Edit"]:
        require(absolute(edit.arguments.get("file_path", ""), cwd) == target + ".prepared", "unexpected editing tool bypasses writer boundary")
        require(before(prepared[0], edit) and before(edit, sync), "prepared body edited outside the window between its write and synchronization")
    require(allocation.value.get("created") is True and allocation.value.get("kind") == "feature" and allocation.value.get("path") == str(Path(target).parent), "requested feature directory was not allocated")
    require(validation.value.get("kind") == "feature" and validation.value.get("path") == target and validation.value.get("status") == "current", "target validation failed")
    require(sync.value.get("plan_type") == "feature" and sync.value.get("path") == target and sync.value.get("status") == "current", "README synchronization failed")
    require(isinstance(sync.value.get("version"), int) and not isinstance(sync.value.get("version"), bool) and sync.value["version"] > 0, "README version missing")
    require(bool(re.fullmatch(r"[0-9a-f]{64}", sync.value.get("content_sha256", ""))), "README content fingerprint missing")
    return allocation, validation, prepared[0], sync


def validate_trace(path: Path, helper_path: Path | None = None) -> None:
    cwd, calls = load_calls(path)
    steps = helper_steps(calls, cwd, helper_path)
    route, contract, lease, provider, lease_path, draft = provider_input(steps, calls)
    response_write = written_response(calls, cwd, lease_path, draft)
    allowed_paths = {lease_path, absolute(TARGET, cwd) + ".prepared"}
    require(all(absolute(call.arguments.get("file_path", ""), cwd) in allowed_paths for call in calls if call.name == "Write"), "unexpected file written outside case contract")
    check = consumed_response(steps, lease_path, response_write)
    target = synchronized_target(steps, calls, cwd)
    sequence = (route, contract, lease, provider, response_write, check, *target)
    require(all(before(a, b) for a, b in zip(sequence, sequence[1:])), "feature steps executed in wrong order")


def validate_feature_runs(document, output_dir: Path) -> None:
    case = next((case for case in document["cases"] if case["name"] == "feature-provider-contract"), None)
    if case is None:
        raise FlowError("feature contract case missing")
    checked = []
    for index, run in enumerate(case["arms"]["with"], 1):
        trace = run.get("tracePath")
        if not isinstance(trace, str):
            raise FlowError("full feature trace path missing")
        path = Path(trace)
        require(path.is_absolute() and path.name == "trace.jsonl" and path.parent.name == "out" and not path.is_symlink(), "invalid full trace carrier")
        try:
            helper = Path(__file__).resolve().parents[1] / "skills/product-discovery/assets/product_state.py"
            validate_trace(path, helper)
        except FlowError as error:
            raise FlowError(f"feature repeat {index}: {error}") from error
        checked.append({"repeat": index, "trace": trace})
    (output_dir / "feature-flow.json").write_text(json.dumps({"case": case["name"], "validated": checked}, indent=2) + "\n", encoding="utf-8")
