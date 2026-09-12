import { useState, useEffect, useCallback } from "react";
import Form from "react-bootstrap/Form";
import Spinner from "react-bootstrap/Spinner";
import Button from "react-bootstrap/Button";
import {
  queryResources,
  createResource,
  updateResource,
  deleteResource,
} from "../../../api/client";
import { request } from "../../../api/client-base";
import type { ResourceRecord, JsonObject } from "../../../types/api";
import AgentTextareas from "./agent/AgentTextareas";
import styles from "./AgentSection.module.css";

const GENDER_OPTIONS = ["Male", "Female"];

interface AgentRecord extends ResourceRecord {
  id: number;
  name: string;
  botname: string;
  bot_personality: string;
  system_instructions: string;
  guardrails_prompt: string;
  use_system_instructions: boolean;
  use_guardrails: boolean;
  use_personality: boolean;
  use_mood: boolean;
  assign_names: boolean;
  use_datetime: boolean;
  gender: string;
  current: boolean;
}

export default function AgentSection() {
  const [agents, setAgents] = useState<AgentRecord[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [botname, setBotname] = useState("");
  const [agentName, setAgentName] = useState("");
  const [botPersonality, setBotPersonality] = useState("");
  const [systemInstructions, setSystemInstructions] = useState("");
  const [guardrailsPrompt, setGuardrailsPrompt] = useState("");
  const [useSystemInstructions, setUseSystemInstructions] = useState(true);
  const [useGuardrails, setUseGuardrails] = useState(true);
  const [usePersonality, setUsePersonality] = useState(true);
  const [useMood, setUseMood] = useState(true);
  const [assignNames, setAssignNames] = useState(true);
  const [useDatetime, setUseDatetime] = useState(true);
  const [gender, setGender] = useState("Male");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const loadAgents = useCallback(async () => {
    try {
      const res = await queryResources("Chatbot");
      const records = (res?.records ?? []) as AgentRecord[];
      setAgents(records);
      // Select the current agent, or the first one
      const current = records.find((r) => r.current) ?? records[0] ?? null;
      if (current) {
        setSelectedId(current.id);
        applyRecord(current);
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAgents();
  }, [loadAgents]);

  function applyRecord(r: AgentRecord) {
    setAgentName(String(r.name ?? ""));
    setBotname(String(r.botname ?? ""));
    setBotPersonality(String(r.bot_personality ?? ""));
    setSystemInstructions(String(r.system_instructions ?? ""));
    setGuardrailsPrompt(String(r.guardrails_prompt ?? ""));
    setUseSystemInstructions(r.use_system_instructions !== false);
    setUseGuardrails(r.use_guardrails !== false);
    setUsePersonality(r.use_personality !== false);
    setUseMood(r.use_mood !== false);
    setAssignNames(r.assign_names !== false);
    setUseDatetime(r.use_datetime !== false);
    setGender(String(r.gender ?? "Male"));
  }

  function persistAll(overrides: Partial<AgentRecord> = {}) {
    if (!selectedId) return;
    updateResource("Chatbot", selectedId, {
      name: agentName,
      botname,
      bot_personality: botPersonality,
      system_instructions: systemInstructions,
      guardrails_prompt: guardrailsPrompt,
      use_system_instructions: useSystemInstructions,
      use_guardrails: useGuardrails,
      use_personality: usePersonality,
      use_mood: useMood,
      assign_names: assignNames,
      use_datetime: useDatetime,
      gender,
      ...overrides,
    } as JsonObject).catch(() => {});
  }

  function persistField(key: string, value: unknown) {
    if (!selectedId) return;
    updateResource("Chatbot", selectedId, { [key]: value } as JsonObject).catch(() => {});
  }

  function handleTextareaChange(key: string, value: string) {
    if (key === "botPersonality") setBotPersonality(value);
    else if (key === "systemInstructions") setSystemInstructions(value);
    else if (key === "guardrailsPrompt") setGuardrailsPrompt(value);
  }

  async function handleSelectAgent(id: number) {
    // Save current agent first
    persistAll();
    // Make selected agent current on server
    try {
      const res = await request<{ record: AgentRecord }>(
        "POST",
        `/api/v1/settings/resources/Chatbot/${id}/make-current`,
      );
      if (res?.record) {
        setSelectedId(id);
        applyRecord(res.record as AgentRecord);
        // Refresh list to update current flags
        const listRes = await queryResources("Chatbot");
        setAgents((listRes?.records ?? []) as AgentRecord[]);
      }
    } catch {
      // ignore
    }
  }

  async function handleCreateAgent() {
    setSaving(true);
    try {
      const res = await createResource("Chatbot", {
        name: `Agent ${agents.length + 1}`,
        botname: "Computer",
        current: false,
      } as JsonObject);
      const newRecord = (res as unknown as { record: AgentRecord })?.record ?? res as unknown as AgentRecord;
      if (newRecord?.id) {
        await loadAgents();
        await handleSelectAgent(newRecord.id);
      }
    } catch {
      // ignore
    } finally {
      setSaving(false);
    }
  }

  async function handleDeleteAgent(id: number) {
    if (agents.length <= 1) return; // always keep at least one
    try {
      await deleteResource("Chatbot", id);
      const remaining = agents.filter((a) => a.id !== id);
      setAgents(remaining);
      if (id === selectedId) {
        // Select another agent — prefer one marked current, else first
        const next = remaining.find((a) => a.current) ?? remaining[0];
        if (next) {
          await handleSelectAgent(next.id);
        }
      }
    } catch {
      // ignore
    }
  }

  const handleResetDefaults = useCallback(async () => {
    if (!selectedId) return;
    try {
      const res = await request<AgentRecord>(
        "POST",
        `/api/v1/settings/resources/Chatbot/${selectedId}/reset-defaults`,
      );
      if (res) applyRecord(res as AgentRecord);
    } catch {
      // ignore
    }
  }, [selectedId]);

  if (loading) {
    return (
      <div className="text-center py-4">
        <Spinner animation="border" size="sm" />
      </div>
    );
  }

  return (
    <div>
      {/* ── Agent selector ── */}
      <div className="d-flex justify-content-between align-items-center mb-2">
        <h6 className="mb-0">Agent Preferences</h6>
        <div className="d-flex gap-1">
          <Button
            variant="outline-secondary"
            size="sm"
            onClick={handleCreateAgent}
            disabled={saving}
            title="Create a new agent"
          >
            + New Agent
          </Button>
          <Button
            variant="outline-danger"
            size="sm"
            onClick={handleResetDefaults}
            title="Reset agent to defaults"
          >
            Reset
          </Button>
        </div>
      </div>

      {agents.length > 1 && (
        <div className="mb-3 d-flex flex-wrap gap-1">
          {agents.map((agent) => (
            <div key={agent.id} className="d-flex align-items-center gap-1">
              <Button
                variant={agent.id === selectedId ? "primary" : "outline-secondary"}
                size="sm"
                onClick={() => handleSelectAgent(agent.id)}
                className={styles.agentBtn}
              >
                {agent.name || agent.botname || `Agent ${agent.id}`}
              </Button>
              {agents.length > 1 && (
                <Button
                  variant="outline-danger"
                  size="sm"
                  onClick={() => handleDeleteAgent(agent.id)}
                  title="Delete this agent"
                  className={styles.deleteBtn}
                >
                  ×
                </Button>
              )}
            </div>
          ))}
        </div>
      )}

      {/* ── Agent fields ── */}
      <div className="mb-3">
        <Form.Group className="mb-2">
          <Form.Label className="small">Agent Name</Form.Label>
          <Form.Control
            size="sm"
            value={agentName}
            onChange={(e) => setAgentName(e.target.value)}
            onBlur={() => persistField("name", agentName)}
            placeholder="e.g. My Assistant"
            className="bg-dark text-light border-secondary"
          />
        </Form.Group>

        <Form.Group className="mb-2">
          <Form.Label className="small">Bot Name</Form.Label>
          <Form.Control
            size="sm"
            value={botname}
            onChange={(e) => setBotname(e.target.value)}
            onBlur={() => persistField("botname", botname)}
            className="bg-dark text-light border-secondary"
          />
        </Form.Group>

        <Form.Group className="mb-2">
          <Form.Check
            type="switch"
            label="Use personality"
            checked={usePersonality}
            onChange={(e) => {
              setUsePersonality(e.target.checked);
              persistField("use_personality", e.target.checked);
            }}
            className="small"
          />
        </Form.Group>

        <Form.Group className="mb-2">
          <Form.Check
            type="switch"
            label="Use mood"
            checked={useMood}
            onChange={(e) => {
              setUseMood(e.target.checked);
              persistField("use_mood", e.target.checked);
            }}
            className="small"
          />
        </Form.Group>

        <Form.Group className="mb-2">
          <Form.Check
            type="switch"
            label="Use system instructions"
            checked={useSystemInstructions}
            onChange={(e) => {
              setUseSystemInstructions(e.target.checked);
              persistField("use_system_instructions", e.target.checked);
            }}
            className="small"
          />
        </Form.Group>

        <Form.Group className="mb-2">
          <Form.Check
            type="switch"
            label="Use guardrails"
            checked={useGuardrails}
            onChange={(e) => {
              setUseGuardrails(e.target.checked);
              persistField("use_guardrails", e.target.checked);
            }}
            className="small"
          />
        </Form.Group>

        <AgentTextareas
          botPersonality={botPersonality}
          systemInstructions={systemInstructions}
          guardrailsPrompt={guardrailsPrompt}
          usePersonality={usePersonality}
          useSystemInstructions={useSystemInstructions}
          useGuardrails={useGuardrails}
          onChange={handleTextareaChange}
          onBlur={() => persistAll()}
        />

        <Form.Group className="mb-2">
          <Form.Check
            type="switch"
            label="Assign names"
            checked={assignNames}
            onChange={(e) => {
              setAssignNames(e.target.checked);
              persistField("assign_names", e.target.checked);
            }}
            className="small"
          />
        </Form.Group>

        <Form.Group className="mb-2">
          <Form.Check
            type="switch"
            label="Use datetime in prompts"
            checked={useDatetime}
            onChange={(e) => {
              setUseDatetime(e.target.checked);
              persistField("use_datetime", e.target.checked);
            }}
            className="small"
          />
        </Form.Group>

        <Form.Group className="mb-2">
          <Form.Label className="small">Gender</Form.Label>
          <Form.Select
            size="sm"
            value={gender}
            onChange={(e) => {
              setGender(e.target.value);
              persistField("gender", e.target.value);
            }}
            className="bg-dark text-light border-secondary"
          >
            {GENDER_OPTIONS.map((g) => (
              <option key={g} value={g}>
                {g}
              </option>
            ))}
          </Form.Select>
        </Form.Group>
      </div>
    </div>
  );
}
