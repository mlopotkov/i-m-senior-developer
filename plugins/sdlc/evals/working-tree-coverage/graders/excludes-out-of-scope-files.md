---
type: regex
name: excludes-out-of-scope-files
target: { source: file, path: review-request-changes/REVIEW-01.md }
pattern: '^(?=[\s\S]*other/outside_scope\.py)(?=[\s\S]*other/untracked_outside\.py)(?![\s\S]*ignored-secret\.txt:\d)'
flags: i
match: contains
---
