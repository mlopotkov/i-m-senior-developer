---
type: regex
name: claims-no-unavailable-domain-pass
target: { source: file, path: review-request-changes/REVIEW-01.md }
pattern: 'Domain pass:\s*(?:`?none available`?|none)'
flags: i
match: contains
---
