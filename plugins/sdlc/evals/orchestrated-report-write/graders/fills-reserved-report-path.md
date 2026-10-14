---
type: regex
name: fills-reserved-report-path
target: { source: file, path: review-request-changes/REVIEW-01.md }
pattern: '^(?=[\s\S]*References loaded:)(?=[\s\S]*Certification boundary)(?=[\s\S]*app/billing\.py)'
match: contains
---
