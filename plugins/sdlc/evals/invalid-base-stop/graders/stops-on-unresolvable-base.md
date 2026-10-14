---
type: regex
name: stops-on-unresolvable-base
target: last_message
pattern: '^(?=[\s\S]*release-candidate)(?![\s\S]*Coverage:[\s*]*(?:complete|empty)\b(?![\s*]*\|))(?![\s\S]*app/\w+\.py:\d)'
flags: i
match: contains
---
