#!/usr/bin/env bash
set -euo pipefail

export GIT_CONFIG_GLOBAL=/dev/null
export GIT_CONFIG_SYSTEM=/dev/null

git init --quiet .
git symbolic-ref HEAD refs/heads/main
git config user.email fixture@example.com
git config user.name 'Fixture Author'

mkdir -p review-request-changes

mkdir -p app app/locale tests

cat > ARCHITECTURE.md <<'DOC'
# Billing — architecture

## Bounded contexts
- rules: owns every eligibility predicate. Lives in `app/rules.py`.
- pricing: computes a total. Lives in `app/pricing.py`.
- reports: renders a summary. Lives in `app/reports.py`.
- api: the HTTP surface. Lives in `app/api.py`.

## Decisions & owners
| Decision | Verdict | Owner |
|---|---|---|
| Who decides that an order qualifies for a discount | committed: `app/rules.py::is_discountable` is the single owner; every caller calls it | rules |

## Notes
A mirror of the discount threshold exists in `docs/pricing.md` as documented
prose, cross-linked to `app/rules.py`. It is a deliberate mirror, not a copy.
DOC

cat > app/rules.py <<'DOC'
DISCOUNT_THRESHOLD = 100


def is_discountable(order):
    return order.total >= DISCOUNT_THRESHOLD and not order.is_refunded
DOC

cat > app/pricing.py <<'DOC'
def final_total(order):
    return order.total
DOC

cat > app/reports.py <<'DOC'
def summary(order):
    return f"order {order.id}"
DOC

cat > app/api.py <<'DOC'
class OrderBase:
    id: str
    total: int


class OrderResponse(OrderBase):
    pass
DOC

cat > app/flow.py <<'DOC'
def advance_manually(state):
    state.step += 1
    return state
DOC

printf '{\n  "order.total": "Sum zakaza",\n  "order.brand": "Acme"\n}\n' > app/locale/ru.json

cat > tests/test_flow.py <<'DOC'
from app.flow import advance_manually


def test_manual_advance():
    state = type("S", (), {"step": 0})()
    assert advance_manually(state).step == 1
DOC

mkdir -p docs
printf '# Pricing\n\nThe discount threshold is owned by `app/rules.py`.\n' > docs/pricing.md

git add .
git commit --quiet -m 'base revision'
git tag base

# 1. pricing re-derives the predicate the architecture assigns to rules
cat > app/pricing.py <<'DOC'
def final_total(order):
    # the eligibility decision is re-derived here instead of calling the owner
    if order.total >= 100 and not order.is_refunded:
        return int(order.total * 0.9)
    return order.total
DOC

# 2. a second, different defect in another in-scope module
cat > app/reports.py <<'DOC'
def summary(order):
    try:
        return f"order {order.id}: {order.total}"
    except Exception:
        return ""
DOC

# 3. schema diff: one safe addition and one breaking rename on a shared base
cat > app/api.py <<'DOC'
class OrderBase:
    id: str
    amount: int          # renamed from total
    currency: str = "EUR"


class OrderResponse(OrderBase):
    note: str | None = None
DOC

# 4. the feature under change is an event-driven advance; the test walks the manual path
cat > app/flow.py <<'DOC'
def advance_manually(state):
    state.step += 1
    return state


def on_step_complete(event, state):
    """The feature: the step advances by itself when the event arrives."""
    if event.kind == "complete":
        state.step += 1
        state.advanced_by_event = True
    return state
DOC

# 5. a translated value carrying a latin dev term, next to a legitimate brand name
printf '{\n  "order.total": "Sum zakaza",\n  "order.markup": "markup po zakazu",\n  "order.brand": "Acme"\n}\n' > app/locale/ru.json
