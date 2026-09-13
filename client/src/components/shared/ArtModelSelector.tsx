import { useState, useEffect } from "react";
import { useArtPrefs } from "../../hooks/useArtPrefs";
import {
  getArtModelOptions,
} from "../../api/client";
import type { ArtOptionsResponse } from "../../api/client";
import Spinner from "react-bootstrap/Spinner";
import styles from "./ArtModelSelector.module.css";

interface ArtModelSelectorProps {
  /** When true, all controls are disabled and a spinner shows. */
  loading?: boolean;
  /** Override the version (for two-way sync). */
  version?: string;
  /** Override the model path. */
  modelPath?: string;
  /** Fired when the user changes version. */
  onVersionChange?: (v: string) => void;
  /** Fired when the user changes model. */
  onModelChange?: (m: string) => void;
}

export default function ArtModelSelector({
  loading,
  version,
  modelPath,
  onVersionChange,
  onModelChange,
}: ArtModelSelectorProps) {
  const [options, setOptions] = useState<ArtOptionsResponse | null>(null);
  const { setArtVersion, setArtModel } = useArtPrefs();

  useEffect(() => {
    getArtModelOptions().then(setOptions).catch(() => {});
  }, []);

  const versionInfo = options?.versions?.find((v) => v.name === version);
  const availableModels = versionInfo?.models ?? [];

  const handleVersion = (v: string) => {
    setArtVersion(v);
    onVersionChange?.(v);
  };

  const handleModel = (m: string) => {
    setArtModel(m);
    onModelChange?.(m);
  };

  return (
    <div className="d-flex align-items-center gap-2">
      {loading && (
        <Spinner animation="border" size="sm" className="text-theme-secondary" />
      )}
      <select
        className={`form-select form-select-sm ${styles.select}`}
        value={version ?? ""}
        disabled={loading}
        onChange={(e) => handleVersion(e.target.value)}
      >
        <option value="">Version...</option>
        {(options?.versions ?? []).map((v) => (
          <option key={v.name} value={v.name}>{v.name}</option>
        ))}
      </select>
      <select
        className={`form-select form-select-sm ${styles.selectWide}`}
        value={modelPath ?? ""}
        disabled={loading || !version || availableModels.length === 0}
        onChange={(e) => handleModel(e.target.value)}
      >
        <option value="">
          {!version ? "Version..." : "Model..."}
        </option>
        {availableModels.map((m) => (
          <option key={m.value} value={m.value}>{m.label}</option>
        ))}
      </select>
    </div>
  );
}
