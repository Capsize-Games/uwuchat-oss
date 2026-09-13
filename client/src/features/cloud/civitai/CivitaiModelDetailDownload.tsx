import { useState } from "react";
import { useDownloadProgress } from "../../edge/downloads/DownloadProgress";
import { useDownloads, type DownloadJob } from "../../edge/downloads/useDownloadState";
import { type CivitaiFile } from "./CivitaiModelDetailTypes";
import { useCivitaiPrefs } from "../../../hooks/useCivitaiPrefs";
import styles from "./CivitaiModelDetailDownload.module.css";

/**
 * Renders Download, Cancel, or Downloaded depending on file status.
 */
export function DownloadButton({
  selectedFile,
  downloads,
  onDownloadClick,
  onCancel,
}: {
  selectedFile: CivitaiFile | null;
  downloads: DownloadJob[];
  onDownloadClick: () => void;
  onCancel: (jobId: string) => void;
}) {
  const { markCompleted, isDownloaded } = useDownloads();
  const downloadUrl = selectedFile?.downloadUrl;

  // Server-reported file existence (authoritative)
  if (selectedFile?.downloaded) {
    return <DownloadedBadge />;
  }

  // localStorage completion history (secondary)
  if (downloadUrl && isDownloaded(downloadUrl)) {
    return <DownloadedBadge />;
  }

  // Active download in progress
  const match = downloadUrl
    ? downloads.find((d) => d.downloadUrl === downloadUrl)
    : null;
  if (match) {
    return (
      <DownloadStatusButton
        jobId={match.jobId}
        onCancel={() => onCancel(match.jobId)}
        checkDone={() => markCompleted(downloadUrl ?? "")}
      />
    );
  }

  return (
    <button
      className="modal-primary-btn"
      onClick={onDownloadClick}
      disabled={!selectedFile?.downloadUrl}
    >
      Download
    </button>
  );
}

function DownloadedBadge() {
  return <div className="modal-downloaded-badge">Downloaded</div>;
}

function DownloadStatusButton({
  jobId,
  onCancel,
  checkDone,
}: {
  jobId: string;
  onCancel: () => void;
  checkDone: () => void;
}) {
  const state = useDownloadProgress(jobId);
  if (state.status === "completed") {
    setTimeout(() => checkDone(), 0);
    return <DownloadedBadge />;
  }
  return (
    <button className="modal-cancel-btn" onClick={onCancel}>
      Cancel
    </button>
  );
}

/**
 * Overlay prompt for entering a CivitAI API key.
 */
export function ApiKeyPrompt({
  onSubmit,
  onCancel,
}: {
  onSubmit: (key: string) => void;
  onCancel: () => void;
}) {
  const [apiKey, setApiKey] = useState("");
  const { setApiKey: persistApiKey } = useCivitaiPrefs();

  const handleSubmit = () => {
    const trimmed = apiKey.trim();
    if (!trimmed) return;
    // Route through the hook so the key is JSON-encoded in
    // sessionStorage and correctly read back by useCivitaiPrefs
    // on subsequent renders / component mounts.
    persistApiKey(trimmed);
    onSubmit(trimmed);
  };

  return (
    <div className={styles.overlay} onClick={onCancel}>
      <div className={styles.dialog} onClick={(e) => e.stopPropagation()}>
        <h4 className={styles.dialogTitle}>
          CivitAI API Key Required
        </h4>
        <p className={styles.dialogText}>
          A CivitAI API key is needed to download this file.
          You can get one from your CivitAI account settings.
          It will be stored in your browser for future downloads.
        </p>
        <input
          type="password"
          placeholder="Enter your CivitAI API key"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") handleSubmit(); }}
          autoFocus
          className={styles.input}
        />
        <div className={styles.btnRow}>
          <button
            className="modal-primary-btn"
            onClick={handleSubmit}
            disabled={!apiKey.trim()}
          >
            Submit & Download
          </button>
          <button className="modal-secondary-btn" onClick={onCancel}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
