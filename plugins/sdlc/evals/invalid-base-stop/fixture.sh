#!/usr/bin/env bash
set -euo pipefail

export GIT_CONFIG_GLOBAL=/dev/null
export GIT_CONFIG_SYSTEM=/dev/null

git init --quiet .
git symbolic-ref HEAD refs/heads/main
git config user.email fixture@example.com
git config user.name 'Fixture Author'

mkdir -p app
printf 'def only_file():\n    return 1\n' > app/only_file.py
git add .
git commit --quiet -m 'base revision'

printf 'def only_file():\n    return 2\n' > app/only_file.py
