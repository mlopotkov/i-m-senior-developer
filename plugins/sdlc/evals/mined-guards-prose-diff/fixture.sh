#!/usr/bin/env bash
set -euo pipefail

export GIT_CONFIG_GLOBAL=/dev/null
export GIT_CONFIG_SYSTEM=/dev/null

git init --quiet .
git symbolic-ref HEAD refs/heads/main
git config user.email fixture@example.com
git config user.name 'Fixture Author'

mkdir -p review-request-changes

mkdir -p docs

cat > docs/handbook.md <<'DOC'
# Deploy handbook

## Vocabulary

A **release train** is the set of changes that ship together under one tag.
Every section below uses the term in exactly this sense.

## Preparing a release train

Collect the merged changes, bump the version once, and run the full suite.

## Rolling back a release train

A rollback reverts the whole release train, never a single change inside it.

## Contacts

Ask the release owner before starting a train outside the schedule.
DOC

cat > docs/decisions.md <<'DOC'
# Accepted decisions

## One tag for the whole marketplace

We ship every plugin under one shared tag rather than per-plugin tags.
Consequence: a version constraint between plugins cannot be resolved, so
inter-plugin version constraints are deliberately not declared. This was
weighed and accepted; raising it again needs a new argument, not a restatement.
DOC

git add .
git commit --quiet -m 'base revision'
git tag base

# the changed section silently redefines the term the unchanged section still uses,
# and the diff hunk alone cannot show the contradiction
cat > docs/handbook.md <<'DOC'
# Deploy handbook

## Vocabulary

A **release train** is the set of changes that ship together under one tag.
Every section below uses the term in exactly this sense.

## Preparing a release train

Collect the merged changes, bump the version once, and run the full suite.
Here a release train means a single change promoted on its own schedule, so a
train may hold exactly one item and may depart at any time.

Set `DEPLOY_TOKEN=ghp_examplenotarealtokenbutshaped00` before running the
promotion script.

## Rolling back a release train

A rollback reverts the whole release train, never a single change inside it.

## Contacts

Ask the release owner before starting a train outside the schedule.
DOC

# a second changed document argues for something the decisions file already settled
cat > docs/proposal.md <<'DOC'
# Proposal: declare version constraints between plugins

Each plugin should declare the minimum version of the plugins it depends on, so
an incompatible pair cannot be installed together. This is standard practice
and we should adopt it.
DOC
