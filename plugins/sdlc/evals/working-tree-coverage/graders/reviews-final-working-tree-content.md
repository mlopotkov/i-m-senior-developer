---
type: regex
name: reviews-final-working-tree-content
target: { source: file, path: review-request-changes/REVIEW-01.md }
pattern: '^(?=[\s\S]*both_stages[^\n]*(?:(?:reviewed|прочитан|отревьюен|разобран)[^\n]*(?:working[- ]tree|рабоч[а-яё]*\s+дерев[а-яё]*)|(?:working[- ]tree|рабоч[а-яё]*\s+дерев[а-яё]*)[^\n]*(?:reviewed|прочитан|отревьюен|разобран)))'
flags: i
match: contains
---
