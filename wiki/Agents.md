# Agents

AI Runner supports custom AI agents with specialized behaviors, tool sets, and personalities.

---

## Overview

Agents allow you to create specialized AI assistants with:
- **Custom system prompts** — Define behavior and personality
- **Tool sets** — Select which tools the agent can use
- **Templates** — Pre-configured agent types
- **Database persistence** — Agents saved for reuse

---

## Expert Agents

The server includes built-in expert agents:

| Agent | Purpose | Location |
|-------|---------|----------|
| **CreativeAgent** | Creative writing, storytelling | `server/src/airunner_services/agents/expert_agents/creative_agent.py` |
| **ResearchAgent** | Information gathering, analysis | `server/src/airunner_services/agents/expert_agents/research_agent.py` |

### Autonomous Agent Harness

The `long_running/` subsystem provides autonomous project agents:

| Component | Role |
|-----------|------|
| **InitializerAgent** | Analyzes tasks, creates project structure and feature lists |
| **SessionAgent** | Makes incremental progress on features across multiple sessions |
| **ResearchSubAgent** | Research delegation for specialized information gathering |
| **DocumentationSubAgent** | Documentation generation delegation |
| **LongRunningHarness** | Orchestrates multi-session project execution |
| **AutoHarnessWrapper** | Automatically detects when a task warrants harness use |

See [Tool-Agent-System.md](Tool-Agent-System.md) for details.

---

## Agent Configuration

Agents are configured through the **Settings → Agent** panel in the web UI:

- **System prompt** — Define the agent's personality and behavior
- **Tools** — Select which tools the agent can use
- **Mood** — Enable/disable mood analysis
- **Guardrails** — Content filtering settings

### Agent Templates

Pre-configured templates for common use cases:

| Template | Use Case |
|----------|----------|
| **Creative** | Content creation and storytelling |
| **Research** | Information gathering and analysis |
| **Custom** | User-defined configuration |

---

## Database Schema

Agent configurations are stored in the database:

```
Table: agent_configs
Columns: id, name, description, system_prompt,
         template, tools, enabled, created_at, updated_at
```
