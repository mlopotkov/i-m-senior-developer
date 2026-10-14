#!/usr/bin/env bash
set -euo pipefail

export GIT_CONFIG_GLOBAL=/dev/null
export GIT_CONFIG_SYSTEM=/dev/null

git init --quiet .
git symbolic-ref HEAD refs/heads/main
git config user.email fixture@example.com
git config user.name 'Fixture Author'

mkdir -p app tests features/FEAT-0002-tag-extractor

cat > pyproject.toml <<'DOC'
[project]
name = "digest"
version = "0.1.0"
DOC

cat > app/extract.py <<'DOC'
def extract_tags(payload: str) -> str:
    """Return the text of the first top-level bracketed group in payload."""
    raise NotImplementedError
DOC

printf '' > tests/__init__.py
printf '' > app/__init__.py

cat > features/FEAT-0002-tag-extractor/ARCH-01.md <<'DOC'
# Tag extractor — architecture

## Bounded contexts
- extract: pulls the first top-level bracketed group out of a payload that may be
  truncated mid-stream. Lives in `app/extract.py`.

## Hand-off contracts
| Caller | Callee | Input | Output | Error mode |
|---|---|---|---|---|
| digest builder | extract | `payload: str` | the text inside the first top-level `[...]` | `ValueError` when no complete group is present |

## Decisions & owners
| Decision | Verdict | Owner |
|---|---|---|
| What counts as the first group when groups nest | committed: the outermost group that opens first, closed by its matching bracket | extract |
| What happens to a bracket inside a quoted string | committed: it is data, never a delimiter | extract |

## Out of scope
- Parsing the payload into a full document model.
DOC

git add .
git commit --quiet -m 'base revision'
