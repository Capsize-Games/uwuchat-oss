# AIRunner Extensions

This directory contains extensions that ship with the open-source AIRunner
repository. They are loaded dynamically by the core framework at runtime.

Each extension lives in its own subdirectory and follows the
convention-based extension pattern described below.

---

## Shipped Extensions

The following extensions are included in this repository:

- **auth** — User registration, login, and JWT-based authentication.
  See [auth/SETUP.md](auth/SETUP.md) for configuration and
  [auth/ARCHITECTURE.md](auth/ARCHITECTURE.md) for the multi-tenant design.
- **conversation_inspector** — Superuser tool to visualize full AI agent
  conversation flows including system prompts, RAG documents, tool calls,
  thinking, and LangGraph node traversal.
- **fastsearch** — Custom search engine integration for web, images, videos,
  news, books, and more.
- **object_storage** — Production asset storage: disables filesystem watchers
  and stores uploaded documents and images in S3, scoped per tenant.
  See [object_storage/README.md](object_storage/README.md).
- **uwu_creator** — Character creation wizard for UwUchat: personality types,
  species, worldview options, and pre-seeded character templates.

---

## How Extensions Work

Extensions are discovered via the `AIRUNNER_EXTENSIONS` setting in `.env`:

```bash
AIRUNNER_EXTENSIONS=extensions.auth.config
```

Each extension must provide an `ExtensionConfig` subclass (like Django's
`AppConfig`) in a `config.py` module. Everything else — routes, models,
middleware, migrations — is auto-discovered by convention.

### Convention-Based Layout

```
extensions/<name>/
├── __init__.py
├── config.py              # ExtensionConfig subclass (REQUIRED)
├── server/
│   ├── __init__.py
│   ├── routes.py          # APIRouter attribute named "router"
│   ├── models.py          # BaseModel subclasses with __tablename__
│   ├── middleware.py      # register(app: FastAPI) function
│   └── migrations/
│       ├── __init__.py
│       └── versions/      # Alembic migration scripts
└── client/
    ├── routes.tsx         # Exports extensionRouteElements (ReactNode[])
    ├── Provider.tsx       # Exports Provider (FC<{children}>)
    ├── api.ts             # API client helpers (optional)
    └── components/        # React components
```

### Auto-Discovery Rules

| If the module exists... | The loader will... |
|---|---|
| `config.py` | Find the `ExtensionConfig` subclass and register the extension |
| `server/routes.py` | Look for a `router: APIRouter` attribute and include it at `/api/v1/{name}` |
| `server/models.py` | Discover all `BaseModel` subclasses and create their tables |
| `server/middleware.py` | Call `register(app: FastAPI)` to install middleware |
| `server/migrations/versions/` | Append to Alembic's `version_locations` for auto-migration |
| `client/routes.tsx` | Import `extensionRouteElements` and render as `<Route>` children |
| `client/Provider.tsx` | Import `Provider` component and wrap the app tree |

### ExtensionConfig

The only required file is `config.py`:

```python
from airunner_services.extensions.config import ExtensionConfig

class MyExtension(ExtensionConfig):
    name = "myextension"
    label = "My Extension"
    description = "What this extension does"
```

---

## Creating Your Own Extension

### Minimal Example

1. **Create the directory structure:**

```
extensions/myapp/
├── __init__.py
├── config.py
└── server/
    ├── __init__.py
    └── routes.py
```

2. **Write `config.py`:**

```python
from airunner_services.extensions.config import ExtensionConfig

class MyAppExtension(ExtensionConfig):
    name = "myapp"
    label = "My Application"
```

3. **Write `server/routes.py`:**

```python
from fastapi import APIRouter

router = APIRouter()

@router.get("/hello")
async def hello():
    return {"message": "Hello from myapp!"}
```

4. **Enable in `.env`:**

```bash
AIRUNNER_EXTENSIONS=extensions.myapp.config
```

5. **Access at:** `GET http://localhost:8080/api/v1/myapp/hello`

### Adding a Database Model

Create `server/models.py`:

```python
from sqlalchemy import Column, Integer, String
from airunner_services.database.base import BaseModel

class MyRecord(BaseModel):
    __tablename__ = "myapp_records"
    # No __public_schema__ = True → lives in tenant schema

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
```

The model's table is automatically created by `setup_database.py`.

### Adding a Migration

Create `server/migrations/versions/001_initial.py` with Alembic `upgrade()`
and `downgrade()` functions. The migration directory is auto-discovered
and appended to `version_locations`.

### Adding a Client Component

Create `client/routes.tsx`:

```tsx
import { Route } from "react-router-dom";
import MyPage from "./components/MyPage";

export const extensionRouteElements = [
  <Route key="mypage" path="/myapp" element={<MyPage />} />,
];
```

Create `client/Provider.tsx` (optional):

```tsx
import { MyContext } from "./context";

export const Provider: FC<{ children: ReactNode }> = ({ children }) => {
  return <MyContext.Provider value={{}}>{children}</MyContext.Provider>;
};
```

The Vite plugin auto-discovers these and generates the appropriate
imports in the `virtual:extensions` module.
