#!/usr/bin/env bash
set -euo pipefail

export GIT_CONFIG_GLOBAL=/dev/null
export GIT_CONFIG_SYSTEM=/dev/null

git init --quiet .
git symbolic-ref HEAD refs/heads/main
git config user.email fixture@example.com
git config user.name 'Fixture Author'

mkdir -p features/FEAT-0001-turn-timer src/scenes src/data

# a stack with no reference in the plugin: a Phaser-style game in TypeScript
cat > package.json <<'DOC'
{
  "name": "board-game",
  "private": true,
  "dependencies": {
    "phaser": "3.80.1"
  },
  "devDependencies": {
    "vitest": "1.6.0"
  }
}
DOC

cat > src/scenes/TurnScene.ts <<'DOC'
import Phaser from "phaser";

export class TurnScene extends Phaser.Scene {
  update(time: number) {
    // turn duration, scoring and the decision to advance all live here
  }
}
DOC

printf '{"turns": []}\n' > src/data/turns.json

cat > features/FEAT-0001-turn-timer/README.md <<'DOC'
# Turn timer with a grace period

## Path

A turn lasts a fixed duration. When it expires the turn advances by itself. A
player who acts within a grace period after expiry still has the action counted
for the turn that just ended.

## Acceptance criteria

- [ ] AC-01: a turn advances by itself when its duration elapses, with no input
- [ ] AC-02: an action inside the grace period counts for the turn that ended
- [ ] AC-03: an action after the grace period counts for the new turn
- [ ] AC-04: the remaining time is readable by the interface at any moment
DOC

git add .
git commit --quiet -m 'base revision'
