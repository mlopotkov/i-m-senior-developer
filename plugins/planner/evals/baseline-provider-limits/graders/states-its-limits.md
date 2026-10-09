---
type: llm
name: states-its-limits
focus: last_message
criteria: |
  The text below is the provider's answer. That it was actually delivered —
  a successful Skill call for planner:product-baseline finishing before this
  answer — is checked by the suite runner, not by you. Judge the content.

  PASS if the answer explicitly says what it cannot support — for example that
  it has no data about real users, that no independent review by other roles
  happened, and that the hypothesis is neither confirmed nor refuted — and
  that it only ordered what the input already carried.

  FAIL if it returns a polished product draft with no such statement, so a
  reader could mistake the shape of the document for grounded work. A single
  vague hedge such as "this is only a draft" is not enough: the answer has to
  name what is missing.

  The statement counts wherever it stands in the answer, inside the structured
  draft or beside it, and it may be worded in any language. An empty or
  truncated answer is a FAIL: there is nothing to judge.
---
