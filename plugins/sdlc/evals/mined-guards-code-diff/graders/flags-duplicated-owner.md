---
type: regex
name: flags-duplicated-owner
target: { source: file, path: review-request-changes/REVIEW-01.md }
pattern: '(?=[\s\S]*app/pricing\.py)(?=[\s\S]*(?:app/rules\.py|is_discountable))(?=[\s\S]*(?:duplicat|source of truth|owner|повторн|владел))(?=[\s\S]*(?:call|delegate|вызов|делег))'
flags: i
match: contains
---
