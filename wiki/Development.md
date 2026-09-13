# Development

This guide covers setting up and contributing to the AI Runner project.

## Project Structure

```
airunner/
├── client/                    # React + Vite frontend
│   ├── src/
│   │   ├── api/              # HTTP/WebSocket API clients
│   │   ├── components/       # UI components
│   │   ├── features/         # Feature modules (art, canvas)
│   │   └── styles/           # SCSS styles
│   └── package.json
├── server/                    # Python backend
│   └── src/airunner_services/
│       ├── api/              # FastAPI server
│       ├── art/              # Image generation pipelines
│       ├── bootstrap/        # Initial data setup
│       ├── config/           # Runtime configuration
│       ├── conversations/    # Chat history
│       ├── database/         # SQLAlchemy + Alembic
│       ├── documents/        # ZIM file scanning
│       ├── downloads/        # Model download system
│       ├── eval/             # LLM evaluation framework
│       ├── ipc/              # Inter-process communication
│       ├── llm/              # LLM orchestration
│       ├── model_management/ # Hardware-aware model loading
│       ├── runtimes/         # Runtime executors and launchers
│       ├── tools/            # LLM tool calling (web search, etc.)
│       └── workers/          # Background workers
├── electron/                  # Desktop Electron wrapper
├── packaging/                 # Linux packaging (AppImage, .deb)
└── scripts/                   # Build and dev scripts
```

## Setting Up the Environment

1. **Clone the repository:**
   ```bash
   git clone https://github.com/<your-org>/<repo>.git
   cd airunner
   ```

2. **Run the install script:**
   ```bash
   ./scripts/install.sh
   ```

3. **Run in development mode:**
   ```bash
   ./scripts/run_web.sh
   ```

### Frontend Development (Hot Reload)

The frontend dev server runs on port 5173 with hot module replacement:

```bash
cd client
npm run dev
```

### Backend Development

Run the backend API server separately:

```bash
cd server
uvicorn airunner_services.api.server:app --reload --port 8080
```

## Environment Variables

Key environment variables for development:

| Variable | Default | Description |
|----------|---------|-------------|
| `AIRUNNER_BASE_PATH` | `~/.local/share/airunner` | Persistent data directory |
| `AIRUNNER_DB_URL` | SQLite path | Database connection string |
| `AIRUNNER_LOG_LEVEL` | `INFO` | Logging verbosity |
| `AIRUNNER_LLM_ON` | `1` | Enable/disable LLM |
| `AIRUNNER_DAEMON` | `0` | Run in daemon mode |
| `AIRUNNER_NO_PRELOAD` | `0` | Skip model preloading |
| `AIRUNNER_DEFAULT_LLM_HF_PATH` | HF path | Default LLM model |
| `PYTORCH_CUDA_ALLOC_CONF` | Config | PyTorch memory config |

## Testing

### Running Tests

```bash
# Run all tests
airunner-tests

# Or directly with pytest
pytest server/src/

# With coverage
airunner-test-coverage-report

# Run eval tests
pytest server/src/ -m eval
```

### Test Markers

| Marker | Description |
|--------|-------------|
| `gui` | Tests requiring Qt GUI (legacy) |
| `fast` | Fast tests with mocked responses |
| `slow` | Tests that take longer |
| `eval` | LLM quality evaluation tests |
| `gpu` | Tests requiring GPU hardware |
| `asyncio` | Async test support |

### Writing Tests

- Unit tests live alongside their component in a `tests/` directory
- Eval tests live in `server/src/airunner_services/eval/tests/`
- Name test files `test_<module_name>.py`
- Mock external dependencies (APIs, databases) for unit tests
- Use `@pytest.mark.eval` for LLM quality tests

## Code Style

- **PEP 8** — Follow Python style guide
- **Line length**: 79 characters
- **Black** formatter configured in `pyproject.toml`
- **Type hints** required for all functions and methods
- **Docstrings** for all public classes and functions

Run quality checks:
```bash
# Code quality report
airunner-quality-report

# Remove unused imports
airunner-remove-unused-imports
```

## Database Migrations

AI Runner uses Alembic for database migrations:

```bash
# Generate a new migration
airunner-generate-migration "Description of changes"

# Apply pending migrations
airunner-migrate
```

Migrations are located in `server/src/airunner_services/database/alembic/versions/`.

## Building for Distribution

### Desktop Bundle

```bash
# Linux AppImage
./scripts/package_linux_appimage.sh

# Windows (PowerShell)
./scripts/package_windows_nsis.ps1
```

### Docker Image

```bash
docker build -t airunner .
```

## Documentation

- **ALL documentation** goes in this wiki repository (`airunner.wiki`)
- Component-level `README.md` files are acceptable for internal developer docs
- Never create `.md` files in the main repository's `docs/` folder (it is git-ignored)

## API Service Layer

The backend exposes a FastAPI REST API. See the [API README](https://github.com/<your-org>/<repo>/blob/develop/server/README.md) for available endpoints.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Write/update tests
5. Ensure all tests pass
6. Submit a pull request

See [CONTRIBUTING.md](https://github.com/<your-org>/<repo>/blob/develop/CONTRIBUTING.md) for details.
