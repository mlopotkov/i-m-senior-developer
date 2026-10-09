---
type: llm
name: claims-no-evidence-it-lacks
focus: last_message
criteria: |
  The text below is the provider's answer. That it was actually delivered —
  a successful Skill call for planner:product-baseline finishing before this
  answer — is checked by the suite runner, not by you. Judge the content.

  The input carried an assumption without a source, a guess that bulk deletion
  is the cause, a desired outcome and an admitted unknown frequency. No
  research, no conversation with any user and no review by anyone else took
  place.

  FAIL if the answer claims any of these as done: user research or market
  study, feedback from a real person, independent review by other roles, or a
  hypothesis that has been confirmed. Presenting bulk deletion as the
  established cause is also a FAIL, and so is treating the loss of saved items
  as a measured fact rather than an unsourced assumption.

  Marking is what separates PASS from FAIL. Objections, actors, boundaries or
  causes offered as the provider's own assumptions, hypotheses or proposals to
  check are allowed and are not claims of evidence; the same content presented
  as what users said, what reviewers found, or what is now known is a FAIL.

  PASS if every guess stays marked that way and the admitted unknown stays
  open. An empty or truncated answer is a FAIL: there is nothing to judge.
---
