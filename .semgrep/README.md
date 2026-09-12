# Semgrep rules for AIRunner security invariants

Two custom rules encode this repo's auth-dependency-injection
conventions.  Generic Semgrep rulesets (`p/python`, `p/security-audit`)
do not catch these — they are specific to how AIRunner routes wire
FastAPI `Depends()` for authentication.

## Rules

| Rule | What it catches |
|---|---|
| `auth-import-error-fallback` | `try/except ImportError` for auth deps that falls back to a weaker guard instead of raising 4xx/5xx |
| `missing-auth-dependency` | `@router.get`/`.post`/… handlers with no `Depends(auth_dep)` parameter |

See [`plans/security-tooling-automation.md`](../plans/security-tooling-automation.md)
Part 1 for rationale and the exact bug classes these rules target.

## Suppressing a false positive

### For `auth-import-error-fallback`

Add this comment on the line immediately before the `try:` block:

    # nosemgrep: auth-import-error-fallback

### For `missing-auth-dependency`

Add this comment on the line immediately before the `@router` decorator:

    # nosemgrep: missing-auth-dependency (<one-line reason>)

The reason must explain why the route is intentionally public (e.g.
"public health endpoint", "uses request.state.account_id from
middleware").  Grep for `nosemgrep: missing-auth-dependency` to
produce the human-reviewable allowlist.
