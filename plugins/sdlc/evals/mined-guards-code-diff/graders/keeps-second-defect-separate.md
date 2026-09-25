---
type: regex
name: keeps-second-defect-separate
target: { source: file, path: review-request-changes/REVIEW-01.md }
pattern: '^(?=[^\n]*app/reports\.py:)(?![^\n]*app/pricing\.py)[^\n]*(?:major|minor|critical|low|high|важност)'
flags: im
match: contains
---
