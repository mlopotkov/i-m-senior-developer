---
type: regex
name: keeps-security-section-and-flags-key
target: { source: file, path: review-request-changes/REVIEW-01.md }
pattern: '(?=[\s\S]*## Security)(?=[\s\S]*DEPLOY_TOKEN)(?=[\s\S]*(?:hardcoded|credential|secret|token-shaped|утеч|секрет|уч[её]тн))'
flags: i
match: contains
---
