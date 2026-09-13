import { useState, useEffect } from "react";
import Form from "react-bootstrap/Form";
import Spinner from "react-bootstrap/Spinner";
import {
  getSingleton,
  updateSingleton,
} from "../../../api/client";
import { useLocalStorage } from "../../../hooks/useLocalStorage";

const THEMES = ["dark", "light", "mint", "neon"] as const;
type ThemeName = (typeof THEMES)[number];

function applyDomTheme(themeName: ThemeName): void {
  document.documentElement.setAttribute("data-theme", themeName);
}

export default function AppearanceSection() {
  const [themeName, setThemeName] = useLocalStorage<ThemeName>(
    "airunner_theme",
    "dark",
  );
  const [loading, setLoading] = useState(true);

  // Apply theme to DOM whenever it changes
  useEffect(() => {
    applyDomTheme(themeName);
  }, [themeName, setThemeName]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const appSettings: Record<string, unknown> =
          await getSingleton("ApplicationSettings");
        if (cancelled) return;
        const raw = appSettings.theme_name as string | undefined;
        const name: ThemeName =
          raw !== undefined && THEMES.includes(raw as ThemeName)
            ? (raw as ThemeName)
            : "dark";
        setThemeName(name);
      } catch {
        // ignore
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [setThemeName]);

  function handleThemeChange(value: string) {
    const name = value as ThemeName;
    setThemeName(name);
    updateSingleton("ApplicationSettings", {
      theme_name: name,
    } as Record<string, unknown>).catch(() => {});
  }

  if (loading) {
    return (
      <div className="text-center py-4">
        <Spinner animation="border" size="sm" />
      </div>
    );
  }

  const labelMap: Record<ThemeName, string> = {
    dark: "Dark",
    light: "Light",
    mint: "Mint",
    neon: "Neon",
  };

  return (
    <div>
      <h6 className="mb-3">Theme</h6>

      <Form.Group className="mb-2">
        <Form.Label className="small">Theme</Form.Label>
        <Form.Select
          size="sm"
          value={themeName}
          onChange={(e) => handleThemeChange(e.target.value)}
          className="bg-dark text-light border-secondary"
        >
          {THEMES.map((t) => (
            <option key={t} value={t}>
              {labelMap[t]}
            </option>
          ))}
        </Form.Select>
      </Form.Group>
    </div>
  );
}
