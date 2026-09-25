"""Fingerprint a Git working tree so two states can be compared exactly.

Written for the review evals: the reviewer must leave the tree it reviews
untouched, and "no mutating command was called" is weaker evidence than the
tree itself being identical afterwards. Everything recorded here is derived
from content and structure, never from time, so a fixture rebuilt from the same
script yields the same fingerprint as the sandbox it was built in.
"""

import hashlib
import json
from pathlib import Path
import subprocess
import sys


def git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=repository,
        text=True,
        capture_output=True,
        check=False,
        env={"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null", "PATH": "/usr/bin:/bin:/usr/local/bin"},
    )
    if result.returncode != 0:
        raise SystemExit(
            f"git {' '.join(arguments)} failed in {repository}: {result.stderr.strip()}"
        )
    return result.stdout


def file_digests(repository: Path) -> dict[str, str]:
    digests: dict[str, str] = {}
    for path in sorted(repository.rglob("*")):
        if path.is_dir() or ".git" in path.relative_to(repository).parts:
            continue
        digests[str(path.relative_to(repository))] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
    return digests


def fingerprint(repository: Path) -> dict[str, object]:
    head_commit = git(repository, "rev-parse", "HEAD").strip()
    tags = sorted(git(repository, "tag").split())
    return {
        "head_ref": git(repository, "symbolic-ref", "HEAD").strip(),
        # Абсолютный отпечаток коммита зависит от времени создания фикстуры,
        # поэтому сравнимо только его отношение к меткам: сдвиг HEAD с метки
        # означает, что кто-то коммитил.
        "head_is_tag": {
            tag: git(repository, "rev-parse", tag).strip() == head_commit
            for tag in tags
        },
        "tags": tags,
        "status": git(repository, "status", "--porcelain=v1", "-uall").splitlines(),
        "index": git(repository, "ls-files", "-s").splitlines(),
        "files": file_digests(repository),
    }


def main(arguments: list[str]) -> int:
    if len(arguments) not in (1, 2):
        print(
            "использование: worktree_fingerprint.py <репозиторий> [<эталон.json>]",
            file=sys.stderr,
        )
        return 64
    current = fingerprint(Path(arguments[0]).resolve())
    if len(arguments) == 1:
        print(json.dumps(current, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    expected = json.loads(Path(arguments[1]).read_text())
    differences = [
        f"{key}: ожидалось {expected.get(key)!r}, получено {value!r}"
        for key, value in current.items()
        if expected.get(key) != value
    ]
    if differences:
        for difference in differences:
            print(difference, file=sys.stderr)
        return 1
    print("рабочее дерево совпадает с эталоном")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
