# AI Runner Contribution Guide

Thank you for your interest in contributing to AI Runner. This guide provides an overview of our project's conventions and practices.

---

## How to make changes and submit them

All development happens directly on `master`; the project does not use a
separate ongoing-work branch.

- **Maintainers** commit straight to `master` — no feature branches or pull
  requests required.
- **Contributors** fork the
  [airunner](https://github.com/Capsize-Games/airunner) repo, create a branch,
  and open a pull request with `master` as the base branch. Use a branch name
  in the style of `[feature/bug/patch]/issue_number-description`.

Example

```bash
git checkout master
git pull
git checkout -b bug/321-some-broken-feature-fix
```

Make your changes, commit them, push your branch, and open a pull request
targeting `master`.

## Pull request requirements
- Submit a pull request (PR) with a clear title and description.
- Target `master` as the base branch.
- Address any feedback provided during the review process.
- PRs must pass all tests and meet coding standards before being merged.

## Reporting bugs and requesting features

Bugs, feature requests, and language support requests are tracked as GitHub
issues. Use the
[issue templates](https://github.com/Capsize-Games/airunner/issues/new/choose)
to open a report:

- [Bug report](https://github.com/Capsize-Games/airunner/issues/new?template=bug_report.md)
- [Feature request](https://github.com/Capsize-Games/airunner/issues/new?template=feature_request.md)
- [Language support](https://github.com/Capsize-Games/airunner/issues/new?template=language_support.md)

## Reporting security vulnerabilities

**Do not open a public issue for a suspected vulnerability.** Security issues
are handled through a private channel, not the public issue tracker. Please
report vulnerabilities privately by emailing:

**security@uwuchat.com**

See [SECURITY.md](SECURITY.md) for the full policy: what to include in a
report, our response expectations (initial acknowledgment within 48 hours,
status update within 5 business days), and coordinated disclosure.

The organization also maintains a
[project board](https://github.com/orgs/Capsize-Games/projects/23) for
planning.

---

## Coding Conventions
We follow the PEP 8 style guide for Python code. You can find the complete
guide [here](https://pep8.org/). Additionally, refer to the
[Style Guide](https://github.com/Capsize-Games/airunner/wiki/Style-guide) in
the wiki (mirrored at `wiki/Style-guide.md` in this repo) for detailed coding
standards specific to this project.

### Key Points from the Style Guide
- **Line Length:** Limit lines to 79 characters.
- **Indentation:** Use 4 spaces per indentation level, never tabs.
- **Naming Conventions:**
  - Variables and functions: `snake_case`
  - Classes: `PascalCase`
  - Constants: `UPPERCASE_WITH_UNDERSCORES`
- **Imports:**
  - Group imports into standard library, third-party, and local imports, separated by blank lines.
  - Use absolute imports whenever possible.
- **Comments and Docstrings:**
  - Use Google-style docstrings for all modules, classes, and functions.
  - Keep inline comments minimal and relevant.
- **Formatting**
  - Use [black](https://pypi.org/project/black/) for code formatting and
    [ruff](https://docs.astral.sh/ruff/) for linting (both configured in
    `pyproject.toml`)

---

## Logging Practices
- Use `self.logger` for logging within classes.
**Examples**:
- `self.logger.debug("...")`
- `self.logger.info("...")`
- `self.logger.warning("...")`
- `self.logger.error("...")`

---

## Services Architecture

AI Runner uses a daemon architecture with a web-based GUI:

- **`server/`**: FastAPI-based daemon that orchestrates LLM, STT, TTS, and
  art workloads. Runs as `airunner-server`.
- **`client/`**: React/TypeScript web GUI built with Vite. Serves
  as the user-facing client that connects to the daemon API.
- **`server/src/airunner_services/runtimes/contracts/`**: Shared transport
  contracts between services and clients.

### Development Workflow

1. Start the daemon:
   ```bash
   ./scripts/dev/run_services.sh
   ```

2. Start the web client in a separate terminal:
   ```bash
   cd client
   npm install
   npm run dev
   ```

3. Open `http://localhost:5173` in your browser.

Or use the combined launcher:
```bash
./scripts/run_web.sh
```

---

## Web GUI Development (Airunner Web Client)

The web GUI is a React/TypeScript application located in `client/`.

- Built with [React](https://react.dev/), [TypeScript](https://www.typescriptlang.org/), and [Vite](https://vitejs.dev/)
- Communicates with the daemon API via REST endpoints
- Source files are under `client/src/`

### Building the Web Client

```bash
cd client
npm install
npm run build
```

### Running in Development

```bash
cd client
npm run dev
```

The dev server runs on `http://localhost:5173` and proxies API calls to the
daemon on port 8188.

---

## Services Development

### Running Tests

```bash
# Service unit tests
./venv/bin/python -m pytest server/tests/test_service_bootstrap.py -v

# Runtime smoke tests
./venv/bin/python scripts/run_tests.py --llm-runtime-smoke
./venv/bin/python scripts/run_tests.py --stt-runtime-smoke
./venv/bin/python scripts/run_tests.py --art-runtime-smoke
./venv/bin/python scripts/run_tests.py --tts-runtime-smoke
```

---

## Testing Guidelines
- Test files are located in `server/tests/` and `client/src/`
  for their respective packages.
- Run Python tests using:
  ```bash
  ./venv/bin/python -m pytest
  ```
  or the unified runner `./venv/bin/python scripts/run_tests.py --unit`.
- Run client tests with `npm test` from `client/`.
- CI runs the client test suite on pushes and pull requests to `master` (see
  `.github/workflows/client-tests.yml`).
- Write new tests for any new features or bug fixes. Follow the structure of existing tests.

---

## Documentation Contributions
- User-facing and architectural documentation lives in the
  [project wiki](https://github.com/Capsize-Games/airunner/wiki), with
  `README.md` files in relevant directories for developer-facing docs.
- Update or add relevant sections in the appropriate `.md` files.
- Ensure that all new features are documented.
- Use clear and concise language.

---

## Commit Message Standards
- A pre-commit hook enforces code rules (formatting and linting) — never
  bypass it with `--no-verify`.
- Use descriptive commit messages that explain the purpose of the change.
- Follow this format:
  ```
  type: Short description

  Detailed explanation of the change (if necessary).
  ```
- Example:
  ```
  feat: Add support for Z-Image generation

  Added support for Z-Image models in the image generation pipeline.
  ```
