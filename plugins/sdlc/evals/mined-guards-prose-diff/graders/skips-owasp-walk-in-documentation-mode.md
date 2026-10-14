---
type: regex
name: skips-owasp-walk-in-documentation-mode
target: { source: file, path: review-request-changes/REVIEW-01.md }
pattern: '(?:OWASP[^\n]{0,140}(?:(?:did|does)[\s*_]*not[\s*_]*run|не[\s*_]*(?:выполнял|проводил|запускал)ся)|(?:(?:did|does)[\s*_]*not[\s*_]*run|не[\s*_]*(?:выполнял|проводил|запускал)ся)[^\n]{0,140}OWASP)'
flags: i
match: contains
---
