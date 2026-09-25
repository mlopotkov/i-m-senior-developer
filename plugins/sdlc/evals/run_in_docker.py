"""Run the SDLC eval suite in its supported container environment."""

import os
from pathlib import Path
import subprocess
import sys


SYSTEM_PATH = (
    "/usr/local/share/npm-global/bin:/usr/local/sbin:/usr/local/bin:"
    "/usr/sbin:/usr/bin:/sbin:/bin"
)
GATEWAY_VARIABLES = (
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_DEFAULT_FABLE_MODEL",
    "ANTHROPIC_DEFAULT_FABLE_MODEL_NAME",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL_NAME",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL_NAME",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL_NAME",
    "CLAUDE_CODE_AUTO_COMPACT_WINDOW",
    "CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY",
    "CLAUDE_CODE_MAX_CONTEXT_TOKENS",
    "CLAUDE_CODE_SUBAGENT_MODEL",
    "ENABLE_TOOL_SEARCH",
)
REQUIRED_VARIABLES = ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL")


def build_docker_command(repo_root: Path, image: str) -> list[str]:
    settings_path = repo_root / "plugins/sdlc/evals/container-settings.json"
    command = [
        "docker",
        "run",
        "--rm",
        "--privileged",
        "--user",
        "0",
        "--volume",
        f"{repo_root}:/workspace",
        "--volume",
        f"{settings_path}:/home/agent/.claude/settings.json:ro",
        "--workdir",
        "/workspace",
        "--env",
        f"PATH={SYSTEM_PATH}",
        "--env",
        "HOME=/home/agent",
        "--env",
        "CLAUDE_CODE_WALNUT_SPIRE=1",
        "--env",
        "CLAUDE_BIN=/usr/local/share/npm-global/bin/claude",
    ]
    for variable in GATEWAY_VARIABLES:
        command.extend(("--env", variable))
    command.extend(
        (
            image,
            "/bin/bash",
            "-c",
            "chmod o+x /home/agent && "
            "exec /usr/bin/python3 plugins/sdlc/evals/run.py",
        )
    )
    return command


def main() -> int:
    missing = [name for name in REQUIRED_VARIABLES if not os.environ.get(name)]
    if missing:
        print(
            "missing required environment variables: " + ", ".join(missing),
            file=sys.stderr,
        )
        return 2

    repo_root = Path(__file__).resolve().parents[3]
    image = os.environ.get("SDLC_EVAL_IMAGE", "ccd-eval-py:latest")
    return subprocess.run(build_docker_command(repo_root, image), check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
