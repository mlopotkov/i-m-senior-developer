"""Запуск полного набора sdlc в проверенном контейнере."""

import os
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from eval_container import (  # noqa: E402
    DEFAULT_IMAGE,
    GATEWAY_VARIABLES,
    REQUIRED_VARIABLES,
    SYSTEM_PATH,
    build_suite_command,
    run_in_container,
)


def build_docker_command(repo_root: Path, image: str) -> list[str]:
    return build_suite_command(repo_root, image, "plugins/sdlc/evals/run.py")


def main() -> int:
    image = os.environ.get("SDLC_EVAL_IMAGE", DEFAULT_IMAGE)
    return run_in_container(REPO_ROOT, image, "plugins/sdlc/evals/run.py")


if __name__ == "__main__":
    raise SystemExit(main())
