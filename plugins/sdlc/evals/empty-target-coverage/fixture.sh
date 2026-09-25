#!/usr/bin/env bash
set -euo pipefail

export GIT_CONFIG_GLOBAL=/dev/null
export GIT_CONFIG_SYSTEM=/dev/null

git init --quiet .
git symbolic-ref HEAD refs/heads/main
git config user.email fixture@example.com
git config user.name 'Fixture Author'

mkdir -p app other
printf 'def untouched():\n    return 1\n' > app/untouched.py
printf 'def elsewhere():\n    return 1\n' > other/elsewhere.py
git add .
git commit --quiet -m 'base revision'
git tag base

# the only change lives outside the reviewed scope
printf 'def elsewhere():\n    return 2\n' > other/elsewhere.py
