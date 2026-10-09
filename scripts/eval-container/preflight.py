#!/usr/bin/env python3
"""Проверка native-песочницы Linux без шлюза и вызовов модели."""
import json
import os
import platform
import re
import runpy
import shlex
import subprocess
import sys
from pathlib import Path

CLAUDE = "/usr/local/share/npm-global/bin/claude"
SHELL = "/bin/bash"
WRAPPER = "/usr/local/bin/bwrap-cap-probe"
SENTINEL = "CLAUDE_EVAL_PREFLIGHT"
PROBE = (
    "import pathlib; "
    f"print({SENTINEL!r}); "
    "print(next(line for line in pathlib.Path('/proc/self/status').read_text().splitlines() "
    "if line.startswith('Seccomp:')))"
)
# Полномочия должны совпадать с CLI: проверка с полными capabilities даёт
# ложный успех, когда настоящий helper не может создать вложенный user namespace.
BWRAP = (
    "/usr/bin/bwrap --die-with-parent --new-session --unshare-all "
    "--cap-drop ALL --cap-add CAP_SETFCAP "
    "--ro-bind / / --proc /proc --dev /dev "
)


class PreflightError(Exception):
    pass


def run(command, env, stage, pass_fds=()):
    try:
        result = subprocess.run(command, env=env, pass_fds=pass_fds,
                                capture_output=True, text=True, timeout=20, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PreflightError(f"{stage}: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "no diagnostic output"
        raise PreflightError(f"{stage}: exit {result.returncode}: {detail}")
    return result.stdout


def bash(script, env, stage, fd=None):
    # Чистая неинтерактивная оболочка не должна подхватить профили пользователя.
    return run([SHELL, "--noprofile", "--norc", "-c", script, "preflight",
                str(fd) if fd is not None else "", stage], env, stage,
               (fd,) if fd is not None else ())


def require_probe(output, stage, seccomp=False):
    lines = output.splitlines()
    if lines.count(SENTINEL) != 1:
        raise PreflightError(f"{stage}: expected one execution sentinel")
    if seccomp:
        modes = [line.split(":", 1)[1].strip() for line in lines if line.startswith("Seccomp:")]
        if modes != ["2"]:
            raise PreflightError(f"{stage}: expected Seccomp mode 2, observed {modes!r}")


def check():
    selected = os.environ.get("CLAUDE_EVAL_INNER_SYS_ADMIN", "0")
    if selected not in ("0", "1"):
        raise PreflightError("CLAUDE_EVAL_INNER_SYS_ADMIN must be 0 or 1 (or unset)")
    expected_mode = "inner-sys-admin" if selected == "1" else "strict"
    try:
        mode = runpy.run_path(WRAPPER)["privilege_mode"]()
    except (OSError, ValueError) as error:
        raise PreflightError(f"managed sandbox authorization: {error}") from error
    if mode != expected_mode:
        raise PreflightError("managed sandbox authorization differs from selected privilege mode")
    bwrap = BWRAP
    if mode == "inner-sys-admin":
        bwrap = bwrap.replace("/usr/bin/bwrap ", WRAPPER + " ", 1)
    if platform.system() != "Linux":
        raise PreflightError("native ELF helper requires Linux")
    machine = platform.machine()
    architectures = {"x86_64": ("amd64", 62), "aarch64": ("arm64", 183)}
    if machine not in architectures:
        raise PreflightError(f"unsupported native architecture: {machine}")
    arch, elf_machine = architectures[machine]
    # Шлюз, токены, proxy и startup hooks не должны влиять на эту проверку.
    env = {"PATH": "/usr/local/share/npm-global/bin:/usr/local/bin:/usr/bin:/bin",
           "HOME": "/home/agent", "SHELL": SHELL, "CLAUDE_CODE_SHELL": SHELL,
           "LANG": "C.UTF-8"}
    versions = {}
    for name, command in (
        ("claude", [CLAUDE, "--version"]), ("node", ["node", "--version"]),
        ("python", ["python3", "--version"]), ("git", ["git", "--version"]),
        ("bash", [SHELL, "--version"]), ("bubblewrap", ["bwrap", "--version"]),
        ("socat", ["socat", "-V"]),
    ):
        output = run(command, env, f"version:{name}")
        versions[name] = output.splitlines()[0] if output.splitlines() else ""
    if versions["claude"] != "2.1.286 (Claude Code)":
        raise PreflightError("version:claude: expected pinned Claude Code 2.1.286")
    git_version = re.match(r"git version (\d+)\.(\d+)", versions["git"])
    if not git_version or tuple(map(int, git_version.groups())) < (2, 31):
        raise PreflightError("version:git: Git >= 2.31 required")
    shell_output = bash(
        "ARGV0=apply-seccomp /usr/bin/python3 -c " +
        shlex.quote("import os; print(os.environ.get('ARGV0', ''))"), env, "shell_dispatch")
    if shell_output != "apply-seccomp\n":
        raise PreflightError("shell_dispatch: Bash did not preserve ARGV0 for a child")
    # Native-помощник вызывается через открытый бинарник Claude: дескриптор 3
    # должен пережить обе оболочки и bubblewrap, иначе проверится другой путь.
    with open(Path(CLAUDE).resolve(), "rb") as native:
        header = native.read(20)
        if (len(header) != 20 or header[:6] != b"\x7fELF\x02\x01" or
                int.from_bytes(header[18:20], "little") != elf_machine):
            raise PreflightError(f"native ELF helper architecture does not match {machine}")
        fd = native.fileno()
        helper = "ARGV0=apply-seccomp /proc/self/fd/3 /usr/bin/python3 -c " + shlex.quote(PROBE)
        output = bash('exec 3<&"$1" || exit 126; ' + helper, env, "helper_seccomp", fd)
        require_probe(output, "helper_seccomp", seccomp=True)
        output = bash(bwrap + "-- /bin/bash --noprofile --norc -c " +
                      shlex.quote(f"printf '%s\\n' {SENTINEL}"), env, "bubblewrap")
        require_probe(output, "bubblewrap")
        output = bash('exec 3<&"$1" || exit 126; ' + bwrap + "-- " +
                      "/bin/bash --noprofile --norc -c " + shlex.quote(helper),
                      env, "combined_seccomp", fd)
        require_probe(output, "combined_seccomp", seccomp=True)
    return {"ok": True, "privilege_mode": mode, "arch": arch, "machine": machine, "shell": SHELL,
            "versions": versions,
            "checks": {"shell_dispatch": True, "helper_seccomp": 2,
                       "bubblewrap": True, "combined_seccomp": 2}}


def main():
    try:
        result = check()
    except (PreflightError, OSError) as exc:
        print(f"preflight: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
