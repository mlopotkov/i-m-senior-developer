---
type: tool_order
name: consumes-before-sync
before:
  tool: Bash
  input_match: 'product_state\.py[\s\S]*check-response[\s\S]*--consume'
after:
  tool: Bash
  input_match: 'product_state\.py[\s\S]*sync\s+feature'
---
