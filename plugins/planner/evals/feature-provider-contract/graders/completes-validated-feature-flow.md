---
type: llm
name: completes-validated-feature-flow
focus: trace
---

PASS only if the trajectory runs route successfully, then response-contract,
then reserves the draft, calls planner:product-baseline, writes the returned
JSON only to DraftLease.path, runs exactly one check-response for feature with
--consume, creates the requested feature directory and README, and runs the
product-state validation required by the skill. If JSON was written, there
must be no later release-response-draft call for that lease.
FAIL on a skipped step, an invalid response, a different output path, a second
cleanup call after consume, or a claimed success without the validated README.
