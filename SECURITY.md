# Security Policy

AIRunner is a framework for building AI-backed websites. This policy
describes which releases receive security support, how to report a
vulnerability privately, and what you can expect from us once a report
is received.

## Supported Versions

AIRunner does not yet ship stable versioned releases. There are no LTS
channels, and no older release line receives backported security fixes.

- **Supported:** the latest published release, and the current state of
  the default branch (`master`).
- **Not supported:** older releases. Fixes land on the default branch
  and are included in the next release. If you run an older release,
  upgrade to the latest one to receive security fixes.

We recommend always running the latest release. If you must run an
older version, you assume the risk of any unpatched vulnerabilities.

## Reporting a Vulnerability

**Do not open a public issue for a suspected vulnerability.** Reports
submitted through the public issue tracker will be redirected to the
private channel below and the public issue will be removed.

Please report vulnerabilities privately by emailing:

**security@uwuchat.com**

### What to include in a report

To help us triage quickly, include as much of the following as you can:

- The affected component and version (e.g. server, client, or a
  specific extension, plus the commit, release, or tag you tested).
- A description of the vulnerability and step-by-step reproduction
  instructions, or a proof-of-concept (PoC).
- The security impact (what an attacker could do, and under what
  conditions).
- Whether the vulnerability is already public, and if so, where.

### What NOT to include

- **Do not disclose the vulnerability publicly** (issue trackers, chat,
  social media, mailing lists) until we have released a fix and you
  have agreed to coordinated disclosure. See
  [Coordinated Disclosure](#coordinated-disclosure) below.
- Do not include personal data of other users in your report.
- Do not test against production instances of the hosted uwuchat.com
  service. Use a local deployment or a staging environment instead.

### Response expectations

- **Initial acknowledgment:** within 48 hours of receiving your report.
- **Status update:** within 5 business days, telling you whether the
  report is accepted, rejected, or needs more information.
- **Coordinated disclosure:** once a fix is available, we will work with
  you to schedule public disclosure.

If we need more information, we will ask. Please follow up if you have
not heard from us within these SLAs.

## Coordinated Disclosure

We ask that you keep a reported vulnerability private until a fix is
available. In exchange, we commit to:

1. **Acknowledging** your report within 48 hours.
2. **Investigating** and triaging it within 5 business days.
3. **Fixing** the issue and releasing a patched version.
4. **Coordinating** public disclosure with you once a fix ships.

If a fix cannot be produced promptly, we will discuss disclosure
timing with you rather than leaving the report open indefinitely.

## Scope

**In scope:**

- The AIRunner server (`server/`).
- The AIRunner client (`client/`).
- Extensions bundled in this repository (`extensions/`).

**Out of scope:**

- Vulnerabilities in third-party dependencies (libraries, packages,
  and other projects this repository depends on). Please report those
  to the upstream project responsible for them.
- The hosted uwuchat.com service. Security issues affecting that
  service should still be reported via **security@uwuchat.com**, but
  note that the hosted service may run different code or configuration
  than this repository.
- Issues that are not security vulnerabilities (bugs, feature requests)
  should use the regular issue tracker instead.

## Security Best Practices for Contributors

Contributors should follow the rules already documented in the repo:

- **Never commit secrets** (API keys, tokens, passwords, certificates).
  Use environment variables or the repository's documented secret
  handling, and ensure `.env` files are never committed.
- **Validate all user-controlled paths** before use, and never allow
  traversal outside the configured base path.
- **Never log sensitive content** (prompts, conversation bodies,
  tokens, or other user content). Log counts, IDs, and state
  transitions instead.
- **Follow the multi-tenant database rules**: never write raw SQL in
  application code, keep migrations idempotent, and never mutate
  `alembic_version` manually.
- **Keep dependencies up to date** and address vulnerability findings
  from the project's scanning tooling (e.g. Trivy, Bandit, gitleaks)
  before merging.

See [`CONTRIBUTING.md`](CONTRIBUTING.md) and the repository wiki for
the full contribution guidelines.
