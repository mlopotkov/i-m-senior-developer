---
type: regex
name: excludes-local-work
target: last_message
pattern: '^(?=[\s\S]*committed_added\.py)(?=[\s\S]*committed_change\.py)(?![\s\S]*(?:local_only|local_untracked|outside_scope)\.py:\d)'
flags: i
match: contains
---
