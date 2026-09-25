#!/usr/bin/env bash
set -euo pipefail

export GIT_CONFIG_GLOBAL=/dev/null
export GIT_CONFIG_SYSTEM=/dev/null

git init --quiet .
git symbolic-ref HEAD refs/heads/main
git config user.email fixture@example.com
git config user.name 'Fixture Author'

mkdir -p app other review-request-changes
printf 'ignored-*.txt\n' > .gitignore
printf 'def staged_only():\n    return 1\n' > app/staged_only.py
printf 'def unstaged_only():\n    return 1\n' > app/unstaged_only.py
printf 'def both_stages():\n    return 1\n' > app/both_stages.py
printf 'def removed_later():\n    return 1\n' > app/removed_later.py
printf 'def renamed_before():\n    return 1\n' > app/renamed_before.py
printf 'def untouched():\n    return 1\n' > app/untouched.py
printf 'def outside_scope():\n    return 1\n' > other/outside_scope.py
git add .
git commit --quiet -m 'base revision'
git tag base

# staged only
printf 'def staged_only():\n    return 2\n' > app/staged_only.py
git add app/staged_only.py

# unstaged only
printf 'def unstaged_only():\n    return 3\n' > app/unstaged_only.py

# staged, then a further unstaged edit on top
printf 'def both_stages():\n    return 2\n' > app/both_stages.py
git add app/both_stages.py
printf 'def both_stages():\n    return 3\n' > app/both_stages.py

# deletion and rename
git rm --quiet app/removed_later.py
git mv app/renamed_before.py app/renamed_after.py

# untracked inside and outside the review scope, plus an ignored file
printf 'def untracked_inside():\n    return 1\n' > app/untracked_inside.py
printf 'def untracked_outside():\n    return 1\n' > other/untracked_outside.py
printf 'ignored payload\n' > app/ignored-secret.txt

# changes outside the review scope must stay outside the review
printf 'def outside_scope():\n    return 2\n' > other/outside_scope.py
