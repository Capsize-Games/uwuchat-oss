"""Privacy-hardening round 2 tests — split across scenario files.

The original monolithic test file has been split into:
- ``test_fhe_shared_scoring.py`` — helpers, fixtures, scoring, candidate cap
- ``test_fhe_public_context_scoping.py`` — public context, email scoping
- ``test_fhe_cross_account_isolation.py`` — per-account key isolation
- ``test_fhe_model_columns.py`` — DocumentChunk / model column verification

Password-strength tests moved to ``extensions/auth/tests/test_password_policy.py``.
"""
