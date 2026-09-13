import { useState, useEffect } from "react";
import Form from "react-bootstrap/Form";
import Spinner from "react-bootstrap/Spinner";
import { getSingleton, updateSingleton } from "@/api/client";

export default function UserSection() {
  const [displayName, setDisplayName] = useState("");
  const [unitSystem, setUnitSystem] = useState("imperial");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const user = await getSingleton("User");
        if (cancelled) return;
        setDisplayName(String(user.display_name ?? ""));
        setUnitSystem(String(user.unit_system ?? "imperial"));
      } catch {
        // ignore
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  function dispatchProfileUpdated() {
    window.dispatchEvent(
      new CustomEvent("uwuchat:user-profile-updated", {
        detail: { display_name: displayName || null },
      }),
    );
  }

  async function persistUser() {
    await updateSingleton("User", {
      display_name: displayName || null,
      unit_system: unitSystem,
    } as Record<string, unknown>)
      .then(() => dispatchProfileUpdated())
      .catch(() => {});
  }

  function handleUnitSystemChange(value: string) {
    setUnitSystem(value);
    updateSingleton("User", {
      display_name: displayName || null,
      unit_system: value,
    } as Record<string, unknown>)
      .then(() => {
        // Tell any open weather panel to refetch immediately — the
        // server doesn't broadcast a weather_data event just because
        // the unit preference changed, so without this the panel keeps
        // showing stale-unit data until the page is reloaded.
        window.dispatchEvent(new Event("uwuchat:unit-system-changed"));
        dispatchProfileUpdated();
      })
      .catch(() => {});
  }

  if (loading) {
    return (
      <div className="text-center py-4">
        <Spinner animation="border" size="sm" />
      </div>
    );
  }

  return (
    <div>
      <h6 className="mb-3">User Settings</h6>

      <Form.Group className="mb-2">
        <Form.Label className="small">Display name</Form.Label>
        <Form.Control
          size="sm"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          onBlur={persistUser}
          className="bg-dark text-light border-secondary"
          placeholder="Your display name"
        />
      </Form.Group>

      <Form.Group className="mb-3">
        <Form.Label className="small">Unit System</Form.Label>
        <Form.Select
          size="sm"
          value={unitSystem}
          onChange={(e) => handleUnitSystemChange(e.target.value)}
          className="bg-dark text-light border-secondary"
        >
          <option value="imperial">Imperial</option>
          <option value="metric">Metric</option>
        </Form.Select>
      </Form.Group>
    </div>
  );
}
