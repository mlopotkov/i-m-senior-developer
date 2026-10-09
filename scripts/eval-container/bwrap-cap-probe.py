#!/usr/bin/python3
"""Явно разрешённая capability только внутри нового user namespace."""

import json
import os
from pathlib import Path
import sys

SETTINGS = Path("/etc/claude-code/managed-settings.json")
WRAPPER = "/usr/local/bin/bwrap-cap-probe"


def privilege_mode():
    # Авторизация — защищённая конфигурация, созданная входом контейнера.
    # Среда дочернего eval-процесса не является источником полномочий.
    try:
        if SETTINGS.is_symlink():
            raise ValueError("managed sandbox settings must not be a symlink")
        data = json.loads(SETTINGS.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return "strict"
    except (OSError, ValueError) as error:
        raise ValueError(f"cannot read managed sandbox authorization: {error}") from error
    sandbox = data.get("sandbox") if isinstance(data, dict) else None
    if (not isinstance(sandbox, dict) or sandbox.get("enabled") is not True or
            sandbox.get("enableWeakerNestedSandbox") is not False or
            sandbox.get("bwrapPath") != WRAPPER):
        raise ValueError("managed sandbox authorization does not select the protected capability wrapper")
    return "inner-sys-admin"


def main(arguments):
    try:
        mode = privilege_mode()
    except ValueError as error:
        raise SystemExit(str(error)) from error
    if mode == "inner-sys-admin" and "--" in arguments:
        separator = arguments.index("--")
        options = arguments[:separator]
        if any(options[i:i + 2] == ["--cap-drop", "ALL"] for i in range(len(options) - 1)):
            if not any(flag in options for flag in ("--unshare-user", "--unshare-all")):
                raise SystemExit("inner CAP_SYS_ADMIN requires an isolated user namespace")
            if not any(options[i:i + 2] == ["--cap-add", "CAP_SYS_ADMIN"] for i in range(len(options) - 1)):
                arguments[separator:separator] = ["--cap-add", "CAP_SYS_ADMIN"]
    os.execv("/usr/bin/bwrap", ["bwrap", *arguments])


if __name__ == "__main__":
    main(sys.argv[1:])
