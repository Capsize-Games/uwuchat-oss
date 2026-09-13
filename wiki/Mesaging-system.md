# Messaging System

AI Runner uses a combination of communication patterns for inter-component messaging.

---

## IPC Messages

The backend uses message-based IPC for communication between the main process and runtime services.

**Location:** `server/src/airunner_services/ipc/messages.py`

The IPC system defines structured message types for:
- Model loading/unloading
- Generation requests
- Status updates
- Error handling

## WebSocket

The web UI communicates with the backend via **WebSocket** for real-time features:

- **Chat** — Streaming LLM responses
- **Image generation** — Progress updates

## REST API

Configuration and management operations use **REST** endpoints via FastAPI:

- Settings CRUD
- Model management
- Download management
- Health checks

## Worker Communication

Background workers communicate via the signal-based system managed by `ServiceWorkerManager`:

```
server/src/airunner_services/service_worker_manager.py
```

This manages worker lifecycle, message routing, and concurrent operation handling across:
- LLM generation workers
- Art generation workers
- TTS/STT workers
- Download workers
- Model scanner workers
