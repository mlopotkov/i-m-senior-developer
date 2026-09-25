#!/usr/bin/env bash
set -euo pipefail

export GIT_CONFIG_GLOBAL=/dev/null
export GIT_CONFIG_SYSTEM=/dev/null

git init --quiet .
git symbolic-ref HEAD refs/heads/main
git config user.email fixture@example.com
git config user.name 'Fixture Author'

mkdir -p app
printf 'def charge(amount):\n    return amount\n' > app/billing.py
git add .
git commit --quiet -m 'base revision'
git tag base

# one defect worth a finding, so the report has substance to carry
printf 'def charge(amount):\n    try:\n        return amount * rate()\n    except Exception:\n        return 0\n' > app/billing.py

# the orchestrator reserves the exact report path as an empty file before the
# role is called; the role must fill it, not create a file of its own choosing
mkdir -p review-request-changes
: > review-request-changes/REVIEW-01.md
