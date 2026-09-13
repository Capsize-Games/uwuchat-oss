"""Auth extension — FastAPI dependency injection.

Provides ``require_auth`` which extracts the authenticated account ID
from the JWT stored in the request's ``Authorization`` header, and
``require_superuser`` which additionally enforces the account's
``is_superuser`` flag.  Both must run after ``auth_middleware`` has
populated ``request.state.account_id``.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request


async def require_auth(request: Request) -> int:
    """FastAPI dependency: return the authenticated account ID.

    The JWT middleware must have already validated the token and
    populated ``request.state.account_id``.  If it hasn't, this
    dependency raises 401.
    """
    account_id = getattr(request.state, "account_id", None)
    if account_id is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
        )
    return account_id


async def require_superuser(account_id: int = Depends(require_auth)) -> int:
    """FastAPI dependency: require the caller to be a superuser.

    Authenticates via :func:`require_auth`, then loads the account from
    the public ``accounts`` table and enforces ``is_superuser``. Returns
    the account ID so admin handlers can still use it. Raises 401 when
    unauthenticated and 403 when the account is not a superuser.

    Usage::

        @router.get("/admin/...", ...)
        async def handler(account_id: int = Depends(require_superuser)):
            ...
    """
    # Imported lazily so importing this module never triggers DB/ORM
    # imports (keeps the dependency cheap to import in tests/tools).
    from airunner_services.database.session import public_session_scope
    from extensions.auth.server.models import Account

    with public_session_scope() as session:
        account = (
            session.query(Account)
            .filter(Account.id == account_id)
            .first()
        )
        is_superuser = bool(account and account.is_superuser)

    if not is_superuser:
        raise HTTPException(
            status_code=403,
            detail="Superuser privileges required",
        )
    return account_id
