# Extensions

AI Runner supports custom extensions that extend functionality through the plugin system.

---

## Extension Directory

Extensions are placed in:
```
~/.local/share/airunner/extensions/
    └── extension_folder/
        ├── __init__.py
        └── plugin.py
```

---

## Writing an Extension

Each extension must define a `Plugin` class:

```python
class Plugin:
    name = "My Extension"
    version = "1.0.0"

    def on_message(self, message: str) -> str:
        # Process message
        return message
```

### Extension Properties

- **`name`** — Display name of the extension
- **`version`** — Extension version
- **`on_message()`** — Optional message handler
- **`on_response()`** — Optional response handler

---

## Debugging Extensions

Check the application logs for extension loading errors. The log level can be adjusted via `AIRUNNER_LOG_LEVEL`.
