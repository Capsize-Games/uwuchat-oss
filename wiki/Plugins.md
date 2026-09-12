# Plugins

AI Runner supports plugin extensions for adding custom functionality. The plugin system is currently based on Python module loading from the extensions directory.

---

## Plugin Directory

Plugins are loaded from:
```
~/.local/share/airunner/extensions/
├── my_plugin/
│   └── plugin.py
└── ...
```

---

## Writing a Plugin

### Basic Structure

Create a `plugin.py` file in a subdirectory under the extensions path:

```python
class Plugin:
    """Example plugin for AI Runner."""

    def __init__(self):
        print("Plugin initialized!")

    def on_message(self, message: str) -> str:
        """Handle incoming messages."""
        return message

    def cleanup(self):
        """Clean up resources on unload."""
        pass
```

### Plugin Lifecycle

1. **Loading** — Plugin loader scans the extensions directory
2. **Instantiation** — `Plugin` class is instantiated
3. **Execution** — Plugin hooks are called as needed
4. **Cleanup** — `cleanup()` called on shutdown

---

## Plugin Hooks

| Hook | Description |
|------|-------------|
| `__init__` | Called when plugin is loaded |
| `on_message` | Called for each user message |
| `on_response` | Called for each AI response |
| `cleanup` | Called on plugin unload |

---

## Best Practices

1. Keep dependencies self-contained within the plugin directory
2. Catch exceptions to prevent crashes
3. Release resources in `cleanup()`
4. Store plugin configuration in the plugin directory
