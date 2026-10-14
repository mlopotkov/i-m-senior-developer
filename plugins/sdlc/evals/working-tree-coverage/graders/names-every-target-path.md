---
type: regex
name: names-every-target-path
target: { source: file, path: review-request-changes/REVIEW-01.md }
pattern: '(?=[\s\S]*app/staged_only\.py)(?=[\s\S]*app/unstaged_only\.py)(?=[\s\S]*app/both_stages\.py)(?=[\s\S]*app/untracked_inside\.py)(?=[\s\S]*app/removed_later\.py)(?=[\s\S]*app/renamed_before\.py)(?=[\s\S]*app/renamed_after\.py)'
match: contains
---
