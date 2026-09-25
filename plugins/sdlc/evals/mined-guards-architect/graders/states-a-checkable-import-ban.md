---
type: regex
name: states-a-checkable-import-ban
target: { source: file, path: features/FEAT-0001-turn-timer/ARCH-01.md }
pattern: '(?=[\s\S]*Forbidden imports)(?=[\s\S]*\|[^\n]*src/[^\n]*\|\s*`?phaser)'
flags: i
match: contains
---
