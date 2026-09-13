import type { ArtOptionsResponse } from "../../../api/client";
import { ArtDropdownPicker } from "./ArtDropdownPicker";
import { Divider } from "./ArtShared";
import styles from "./ModelRows.module.css";

interface Props {
  version: string;
  modelPath: string;
  scheduler: string;
  schedulerOptions: { label: string; value: string }[];
  loading: boolean;
  artOptions: ArtOptionsResponse | null;
  onVersionChange: (v: string) => void;
  onModelChange: (m: string) => void;
  onSchedulerChange: (s: string) => void;
}

export function ModelRows({ version, modelPath, scheduler, schedulerOptions, loading, artOptions, onVersionChange, onModelChange, onSchedulerChange }: Props) {
  const versionInfo = artOptions?.versions?.find((v) => v.name === version);
  const availableModels = versionInfo?.models ?? [];

  if (loading) {
    return (
      <div className={`${styles.row} justify-content-center p-1`}>
        <div className={`spinner-border spinner-border-sm ${styles.spinner}`} role="status" />
      </div>
    );
  }

  return (
    <div className={styles.row}>
      <ArtDropdownPicker
        value={version}
        placeholder="Version…"
        options={artOptions?.versions?.map((v) => ({ label: v.name, value: v.name })) ?? []}
        onChange={onVersionChange}
      />
      <Divider />
      <ArtDropdownPicker
        value={modelPath}
        placeholder={version ? "Model…" : "Version…"}
        options={availableModels}
        onChange={onModelChange}
        disabled={!version || availableModels.length === 0}
      />
      <Divider />
      <ArtDropdownPicker
        value={scheduler}
        placeholder="Scheduler…"
        options={schedulerOptions}
        onChange={onSchedulerChange}
        disabled={!version || schedulerOptions.length === 0}
      />
    </div>
  );
}
