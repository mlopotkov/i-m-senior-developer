#!/usr/bin/env bash
set -euo pipefail

export GIT_CONFIG_GLOBAL=/dev/null
export GIT_CONFIG_SYSTEM=/dev/null

git init --quiet .
git symbolic-ref HEAD refs/heads/main
git config user.email fixture@example.com
git config user.name 'Fixture Author'

mkdir -p app other
printf 'def committed_change():\n    return 1\n' > app/committed_change.py
printf 'def local_only():\n    return 1\n' > app/local_only.py
printf 'def outside_scope():\n    return 1\n' > other/outside_scope.py
git add .
git commit --quiet -m 'base revision'
git tag base

printf 'def committed_change():\n    return 2\n' > app/committed_change.py
printf 'def committed_added():\n    return 1\n' > app/committed_added.py
git add app/committed_change.py app/committed_added.py
git commit --quiet -m 'commit under review'

# local work that the commit range must not pick up
printf 'def local_only():\n    return 99\n' > app/local_only.py
printf 'def local_untracked():\n    return 1\n' > app/local_untracked.py
printf 'def outside_scope():\n    return 2\n' > other/outside_scope.py
