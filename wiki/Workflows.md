# Workflow Templates

Workflow templates provide pre-configured agent patterns for common AI tasks.

---

## Available Templates

### RAG Workflow

Retrieval-Augmented Generation workflow that searches documents and generates responses based on retrieved context.

**Flow:**
```
User Input → RAG Search → LLM Generation → Output
```

**Use Cases:**
- Question answering over documents
- Knowledge base chat
- Document-grounded responses

### Agent Loop Workflow

Autonomous agent workflow with reasoning, tool selection, and execution feedback loop.

**Flow:**
```
Task Input → Agent Reasoning → Tool Execution → Loop until complete
```

**Use Cases:**
- Multi-step task completion
- Research and analysis
- Autonomous problem solving

---

## Expert Agents

The server includes specialized agent implementations:

| Agent | Type | Description |
|-------|------|-------------|
| **CreativeAgent** | Content creation | Writing, storytelling, creative content |
| **ResearchAgent** | Information gathering | Web search, fact synthesis |

These agents extend from the base expert agent in `server/src/airunner_services/agents/expert_agent.py`.
