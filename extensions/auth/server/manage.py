"""Auth extension — account management CLI.

The auth extension has no web framework behind it (no Django ``manage.py``),
so this module is the equivalent: a small command-line tool for creating and
administering accounts directly against the database. It is the supported way
to bootstrap the first admin/superuser, since self-service registration always
creates a plain (non-superuser) account.

Run it inside the server container (it needs the same DB env as the app):

    # convenience wrapper
    ./scripts/docker.sh auth create-user --email me@example.com \\
        --username me --password 'secret123' --superuser

    # or directly
    python -m extensions.auth.server.manage create-user --email ...

Commands:
    create-user   Create an account (+ provision its tenant schema).
    promote       Grant or revoke superuser on an existing account.
    list          List accounts.
    repair-tenant Re-run tenant provisioning for an account (idempotent).
    delete        Delete an account row (does not drop the tenant schema).
    send-test     Send a test email via SMTP (verifies configuration).

This tool talks to the public ``accounts`` table via ``public_session_scope``
and reuses the same hashing and tenant-provisioning code paths the HTTP
register endpoint uses, so CLI-created accounts are identical to registered
ones.
"""

from __future__ import annotations

import argparse
import getpass
import sys

from airunner_services.database.session import public_session_scope

from extensions.auth.server.email import send_email
from extensions.auth.server.models import Account
from extensions.auth.server.routes import (
    AccountConflictError,
    AccountValidationError,
    create_account,
    _provision_tenant,
)


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def cmd_create_user(args: argparse.Namespace) -> int:
    email = _normalize_email(args.email)
    username = args.username.strip()
    password = args.password or getpass.getpass("Password: ")

    # Reuse the exact account-creation + tenant-provisioning path the admin
    # HTTP route uses, so CLI- and API-created accounts can't drift.
    try:
        account_id, tenant_schema = create_account(
            email,
            password,
            username,
            is_superuser=bool(args.superuser),
            is_verified=not args.unverified,
            provision_tenant=not args.no_tenant,
        )
    except (AccountValidationError, AccountConflictError) as exc:
        raise SystemExit(f"error: {exc}")

    print(
        f"created account id={account_id} email={email} "
        f"username={username} superuser={bool(args.superuser)} "
        f"verified={not args.unverified} tenant={tenant_schema}"
    )
    return 0


def cmd_promote(args: argparse.Namespace) -> int:
    email = _normalize_email(args.email)
    grant = not args.demote
    with public_session_scope() as session:
        account = (
            session.query(Account).filter(Account.email == email).first()
        )
        if account is None:
            raise SystemExit(f"error: no account with email {email}")
        account.is_superuser = grant
        session.add(account)
        account_id = account.id
    print(
        f"{'granted' if grant else 'revoked'} superuser for "
        f"{email} (id={account_id})"
    )
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    with public_session_scope() as session:
        accounts = session.query(Account).order_by(Account.id).all()
        rows = [
            (
                a.id,
                a.email,
                a.username,
                "super" if a.is_superuser else "user",
                "verified" if a.is_verified else "unverified",
                "active" if a.is_active else "disabled",
                a.tenant_schema,
            )
            for a in accounts
        ]
    if not rows:
        print("(no accounts)")
        return 0
    header = ("ID", "EMAIL", "USERNAME", "ROLE", "VERIFIED", "STATE", "TENANT")
    widths = [
        max(len(str(r[i])) for r in rows + [header]) for i in range(len(header))
    ]
    line = "  ".join(str(header[i]).ljust(widths[i]) for i in range(len(header)))
    print(line)
    for r in rows:
        print("  ".join(str(r[i]).ljust(widths[i]) for i in range(len(r))))
    return 0


def cmd_repair_tenant(args: argparse.Namespace) -> int:
    email = _normalize_email(args.email)
    with public_session_scope() as session:
        account = (
            session.query(Account).filter(Account.email == email).first()
        )
        if account is None:
            raise SystemExit(f"error: no account with email {email}")
        tenant_schema = account.tenant_schema
    _provision_tenant(tenant_schema)
    print(f"re-provisioned tenant schema {tenant_schema} for {email}")
    return 0


def cmd_send_test(args: argparse.Namespace) -> int:
    """Send a test email via SMTP to verify configuration."""
    email = _normalize_email(args.email)
    subject = "Auth extension SMTP test"
    body = "This is a test email from the auth extension."
    sent = send_email(email, subject, "", body)
    if sent:
        print(f"test email sent to {email}")
        return 0
    print(f"failed to send test email to {email}")
    return 1


def cmd_delete(args: argparse.Namespace) -> int:
    email = _normalize_email(args.email)
    with public_session_scope() as session:
        account = (
            session.query(Account).filter(Account.email == email).first()
        )
        if account is None:
            raise SystemExit(f"error: no account with email {email}")
        if not args.yes:
            confirm = input(f"Delete account {email} (id={account.id})? [y/N] ")
            if confirm.strip().lower() not in {"y", "yes"}:
                print("aborted")
                return 1
        session.delete(account)
    print(f"deleted account {email}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="auth-manage",
        description="Auth extension account management.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_create = sub.add_parser("create-user", help="Create an account.")
    p_create.add_argument("--email", required=True)
    p_create.add_argument("--username", required=True)
    p_create.add_argument(
        "--password",
        help="Password (prompted securely if omitted).",
    )
    p_create.add_argument(
        "--superuser",
        action="store_true",
        help="Mark the account as a superuser.",
    )
    p_create.add_argument(
        "--unverified",
        action="store_true",
        help="Create the account as email-unverified (default: verified).",
    )
    p_create.add_argument(
        "--no-tenant",
        action="store_true",
        help="Skip tenant-schema provisioning (account row only).",
    )
    p_create.set_defaults(func=cmd_create_user)

    p_promote = sub.add_parser(
        "promote", help="Grant/revoke superuser on an account."
    )
    p_promote.add_argument("--email", required=True)
    p_promote.add_argument(
        "--demote",
        action="store_true",
        help="Revoke superuser instead of granting it.",
    )
    p_promote.set_defaults(func=cmd_promote)

    p_list = sub.add_parser("list", help="List accounts.")
    p_list.set_defaults(func=cmd_list)

    p_repair = sub.add_parser(
        "repair-tenant",
        help="Re-run tenant provisioning for an account (idempotent).",
    )
    p_repair.add_argument("--email", required=True)
    p_repair.set_defaults(func=cmd_repair_tenant)

    p_delete = sub.add_parser("delete", help="Delete an account row.")
    p_delete.add_argument("--email", required=True)
    p_delete.add_argument(
        "--yes", action="store_true", help="Do not prompt for confirmation."
    )
    p_delete.set_defaults(func=cmd_delete)

    p_send_test = sub.add_parser(
        "send-test", help="Send a test email via SMTP."
    )
    p_send_test.add_argument("--email", required=True)
    p_send_test.set_defaults(func=cmd_send_test)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
