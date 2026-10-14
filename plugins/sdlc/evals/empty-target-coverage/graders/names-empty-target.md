---
type: regex
name: names-empty-target
target: last_message
pattern: '^(?=[\s\S]*Major:[\s*]*0)(?=[\s\S]*Minor:[\s*]*0)(?![\s\S]*(?:untouched|elsewhere)\.py:\d)'
flags: i
match: contains
---
