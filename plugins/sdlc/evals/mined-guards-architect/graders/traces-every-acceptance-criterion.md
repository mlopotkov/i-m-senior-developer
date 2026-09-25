---
type: regex
name: traces-every-acceptance-criterion
target: { source: file, path: features/FEAT-0001-turn-timer/ARCH-01.md }
pattern: '(?=[\s\S]*(?:Requirements trace|Acceptance criterion))(?=[\s\S]*AC-01)(?=[\s\S]*AC-02)(?=[\s\S]*AC-03)(?=[\s\S]*AC-04)(?=[\s\S]*(?:Implementing context|реализующ(?:ий|его) контекст))'
flags: i
match: contains
---
