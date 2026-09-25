---
type: tool_used
name: makes-no-mutating-git-call
tool: Bash
input_match: 'git (?:checkout|reset|add|commit|push|apply|merge|rebase|mv|rm)\b|git (?:stash|worktree)(?:\s+(?!list\b|show\b)\S|\s*$)'
min: 0
max: 0
---
