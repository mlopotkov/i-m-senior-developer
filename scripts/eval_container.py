"""Общий запуск контейнерных eval с проверкой среды до расходов."""

import json
import os
import re
import shlex
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid

SYSTEM_PATH = (
    "/usr/local/share/npm-global/bin:/usr/local/sbin:/usr/local/bin:"
    "/usr/sbin:/usr/bin:/sbin:/bin"
)
GATEWAY_VARIABLES = (
    "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
    "ANTHROPIC_DEFAULT_FABLE_MODEL", "ANTHROPIC_DEFAULT_FABLE_MODEL_NAME",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL", "ANTHROPIC_DEFAULT_HAIKU_MODEL_NAME",
    "ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_OPUS_MODEL_NAME",
    "ANTHROPIC_DEFAULT_SONNET_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL_NAME",
    "CLAUDE_CODE_AUTO_COMPACT_WINDOW", "CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY",
    "CLAUDE_CODE_MAX_CONTEXT_TOKENS", "CLAUDE_CODE_SUBAGENT_MODEL", "ENABLE_TOOL_SEARCH",
    "MAX_COST_USD",
)
REQUIRED_VARIABLES = ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL")
SETTINGS_PATH = "plugins/sdlc/evals/container-settings.json"
DEFAULT_IMAGE = "ccd-eval-native:2.1.286"
CHECKS = {
    "shell_dispatch": True,
    "helper_seccomp": 2,
    "bubblewrap": True,
    "combined_seccomp": 2,
}


class ContainerError(RuntimeError):
    pass


class ContainerTimeout(ContainerError):
    pass


def environment_arguments() -> list[str]:
    return [
        "--env", f"PATH={SYSTEM_PATH}",
        "--env", "HOME=/home/agent",
        "--env", "SHELL=/bin/bash",
        "--env", "CLAUDE_CODE_SHELL=/bin/bash",
        "--env", "CLAUDE_BIN=/usr/local/share/npm-global/bin/claude",
    ]


def privilege_mode() -> str:
    value = os.environ.get("CLAUDE_EVAL_INNER_SYS_ADMIN", "0")
    if value not in ("0", "1"):
        raise ContainerError("CLAUDE_EVAL_INNER_SYS_ADMIN must be 0 or 1 (or unset)")
    return "inner-sys-admin" if value == "1" else "strict"


def managed_settings_script() -> str:
    settings = json.dumps({"sandbox": {
        "enabled": True, "enableWeakerNestedSandbox": False,
        "bwrapPath": "/usr/local/bin/bwrap-cap-probe",
    }})
    return ("mkdir -p /etc/claude-code && printf '%s\\n' " + shlex.quote(settings) +
            " > /etc/claude-code/managed-settings.json && "
            "chmod 444 /etc/claude-code/managed-settings.json && ")


def build_suite_command(repo_root: Path, image: str, runner: str,
                        results_folder: Path | None = None) -> list[str]:
    mode = privilege_mode()
    command = [
        "docker", "run", "--rm", "--privileged", "--user", "0",
        "--volume", f"{repo_root}:/workspace",
        "--volume", f"{repo_root / SETTINGS_PATH}:/home/agent/.claude/settings.json:ro",
        "--workdir", "/workspace",
        *environment_arguments(),
        "--env", "CLAUDE_CODE_WALNUT_SPIRE=1",
        "--env", "CLAUDE_EVAL_INNER_SYS_ADMIN=" + ("1" if mode == "inner-sys-admin" else "0"),
    ]
    for variable in GATEWAY_VARIABLES:
        command.extend(("--env", variable))
    setup = "chmod o+x /home/agent && "
    if mode == "inner-sys-admin":
        setup += managed_settings_script()
    if results_folder is not None:
        plugin = Path(runner).parts[1].upper()
        destination = "/workspace/" + results_folder.relative_to(repo_root).as_posix()
        command.extend(("--env", f"{plugin}_EVAL_RESULTS_ROOT={destination}",
                        "--env", "CLAUDE_BIN=/usr/local/bin/claude-eval-keep"))
        command.remove("--rm")
    command.extend((image, "/bin/bash", "-c",
                    setup + f"exec /usr/bin/python3 {runner}"))
    return command


def build_preflight_command(image: str) -> list[str]:
    # Проверка не должна зависеть от шлюза или получить настоящие учётные
    # данные из родительской среды либо выбранного пользователем образа.
    mode = privilege_mode()
    command = [
        "docker", "run", "--rm", "--privileged", "--network", "none",
        "--env", "CLAUDE_EVAL_INNER_SYS_ADMIN=" + ("1" if mode == "inner-sys-admin" else "0"),
        "--read-only", "--user", "0", *environment_arguments(),
        "--env", "ANTHROPIC_AUTH_TOKEN=", "--env", "ANTHROPIC_API_KEY=",
        "--env", "ANTHROPIC_BASE_URL=",
    ]
    if mode == "inner-sys-admin":
        command.extend(("--tmpfs", "/etc/claude-code:rw,nosuid,nodev,noexec",
                        image, "/bin/bash", "--noprofile", "--norc", "-c",
                        managed_settings_script() +
                        "exec /usr/bin/python3 /usr/local/lib/claude-eval/preflight.py"))
    else:
        command.extend((image, "/usr/bin/python3", "/usr/local/lib/claude-eval/preflight.py"))
    return command


def capture(command: list[str], timeout: int) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True,
                                check=False, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        raise ContainerTimeout(f"container check timed out after {timeout}s") from error
    except OSError as error:
        raise ContainerError(f"cannot launch container check: {error}") from error
    if result.returncode:
        detail = (result.stderr or result.stdout or "no diagnostic output").strip()
        raise ContainerError(f"container check failed ({result.returncode}): {detail}")
    return result.stdout.strip()


def native_image(image: str) -> dict[str, str]:
    aliases = {"aarch64": "arm64", "arm64": "arm64", "x86_64": "amd64", "amd64": "amd64"}
    daemon = capture(["docker", "info", "--format", "{{.Architecture}}"], 30)
    fields = capture(["docker", "image", "inspect", image, "--format",
                      "{{.Architecture}} {{.Id}}"], 30).split()
    if len(fields) != 2 or daemon not in aliases or fields[0] not in aliases:
        raise ContainerError("cannot identify supported daemon/image architecture")
    if aliases[daemon] != aliases[fields[0]]:
        raise ContainerError(f"image architecture {fields[0]} differs from daemon {daemon}; build a native image")
    return {"daemon_architecture": aliases[daemon], "image_architecture": aliases[fields[0]],
            "image_id": fields[1]}


def require_settings(repo_root: Path) -> None:
    path = repo_root / SETTINGS_PATH
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ContainerError(f"cannot read eval sandbox settings: {path}: {error}") from error
    sandbox = data.get("sandbox", {}) if isinstance(data, dict) else {}
    if not isinstance(sandbox, dict) or sandbox.get("enabled") is not True or sandbox.get("bwrapPath") != "/usr/bin/bwrap":
        raise ContainerError("eval settings must enable sandbox and use stock /usr/bin/bwrap")


def remove_container(name: str) -> None:
    try:
        result = subprocess.run(["docker", "rm", "-f", name], capture_output=True,
                                text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ContainerError(f"cannot confirm removal of container {name}: {error}") from error
    if result.returncode and "No such container" not in result.stderr:
        raise ContainerError(f"cannot remove container {name}: {result.stderr.strip()}")


def require_preflight(image: str) -> dict:
    name = "claude-eval-preflight-" + uuid.uuid4().hex
    command = build_preflight_command(image)
    command[2:2] = ["--name", name]
    try:
        text = capture(command, 90)
    except (ContainerTimeout, KeyboardInterrupt):
        # Timeout завершает клиент Docker, но не обязательно контейнер daemon.
        remove_container(name)
        raise
    try:
        proof = json.loads(text)
    except ValueError as error:
        raise ContainerError("preflight did not return JSON proof") from error
    if not isinstance(proof, dict) or proof.get("ok") is not True or proof.get("checks") != CHECKS:
        raise ContainerError("preflight did not prove native dispatch, seccomp and bubblewrap")
    if proof.get("privilege_mode") != privilege_mode():
        raise ContainerError("preflight privilege mode differs from selected mode")
    return {key: proof[key] for key in ("ok", "checks", "privilege_mode", "versions", "arch", "machine", "shell")
            if key in proof}


def save_proof(repo_root: Path, runner: str, identity: dict, proof: dict) -> Path:
    results = repo_root / Path(runner).parent / "results"
    results.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix="environment-", dir=results))
    (folder / "environment.json").write_text(
        json.dumps({**identity, **proof}, indent=2) + "\n", encoding="utf-8"
    )
    return folder


def copy_traces(name: str, folder: Path) -> None:
    # Не копируем HOME, рабочие каталоги кейсов или всё дерево /tmp: только
    # заявленный CLI файл трассы из результата именно этого запуска.
    for aggregate in folder.glob("run-*/aggregate-result.json"):
        data = json.loads(aggregate.read_text(encoding="utf-8"))
        for case_index, case in enumerate(data.get("cases", [])):
            for arm_index, runs in enumerate(case.get("arms", {}).values()):
                for run_index, run in enumerate(runs):
                    source = run.get("tracePath")
                    if not isinstance(source, str) or not re.fullmatch(
                            r"/tmp/claude-eval-[A-Za-z0-9_-]+/out/trace\.jsonl", source):
                        raise ContainerError("unexpected CLI tracePath; refusing to copy other files")
                    target = folder / "full-traces" / f"case-{case_index}-arm-{arm_index}-run-{run_index}"
                    target.mkdir(parents=True, exist_ok=False)
                    trace = target / "trace.jsonl"
                    capture(["docker", "cp", f"{name}:{source}", str(trace)], 30)
                    if trace.is_symlink():
                        trace.unlink()
                        raise ContainerError("trace capture returned a symlink, not a trace file")
                    trace.chmod(0o600)
                    text = trace.read_text(encoding="utf-8")
                    for variable in ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY"):
                        secret = os.environ.get(variable)
                        if secret:
                            text = text.replace(secret, "[REDACTED]")
                    trace.write_text(text, encoding="utf-8")


def run_paid_container(command: list[str], folder: Path | None = None) -> int:
    name = "claude-eval-suite-" + uuid.uuid4().hex
    command[2:2] = ["--name", name]
    try:
        code = subprocess.run(command, check=False).returncode
    except (KeyboardInterrupt, OSError):
        # Модель внутри daemon продолжит расходовать средства, если убить только клиент.
        remove_container(name)
        raise
    if folder is not None:
        try:
            copy_traces(name, folder)
        except (ContainerError, OSError, ValueError) as error:
            raise ContainerError(f"trace capture failed for {name}; launch evidence incomplete: {error}") from error
        finally:
            # Даже остановленный контейнер хранит переданный токен в metadata.
            remove_container(name)
    return code


def run_in_container(repo_root: Path, image: str, runner: str) -> int:
    missing = [key for key in REQUIRED_VARIABLES if not os.environ.get(key)]
    if missing:
        print("missing required environment variables: " + ", ".join(missing), file=sys.stderr)
        return 2
    try:
        privilege_mode()
        require_settings(repo_root)
        identity = native_image(image)
        checked_image = identity["image_id"]
        proof = require_preflight(checked_image)
        folder = save_proof(repo_root, runner, identity, proof)
        print(f"container preflight passed: {folder}", flush=True)
        return run_paid_container(build_suite_command(repo_root, checked_image, runner, folder), folder)
    except KeyboardInterrupt:
        return 130
    except (ContainerError, OSError) as error:
        print(f"eval container: {error}", file=sys.stderr)
        return 1
