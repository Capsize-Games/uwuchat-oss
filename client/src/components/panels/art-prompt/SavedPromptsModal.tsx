import { useState, useEffect, useCallback } from "react";
import {
  listSavedPrompts,
  deleteSavedPrompt,
  type SavedPrompt,
} from "../../../api/art";
import LucideIcon from "../../shared/LucideIcon";
import styles from "./SavedPromptsModal.module.css";

interface Props {
  version: string;
  onLoad: (p: SavedPrompt) => void;
  onClose: () => void;
}

export default function SavedPromptsPanel({
  version,
  onLoad,
  onClose,
}: Props) {
  const [prompts, setPrompts] = useState<SavedPrompt[]>([]);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState<number | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listSavedPrompts(version || undefined);
      setPrompts(data.prompts ?? []);
    } catch {
      setPrompts([]);
    } finally {
      setLoading(false);
    }
  }, [version]);

  useEffect(() => { reload(); }, [reload]);

  const handleDelete = async (id: number) => {
    setDeleting(id);
    try {
      await deleteSavedPrompt(id);
      setPrompts((prev) => prev.filter((p) => p.id !== id));
    } catch {
    } finally {
      setDeleting(null);
    }
  };

  return (
    <div className="d-flex flex-column h-100">
      {/* Sticky header */}
      <div
        className={`sticky-top flex-shrink-0 d-flex align-items-center bg-theme-panel border-b-theme ${styles.header}`}
      >
        <span className="text-panel-label text-uppercase">
          Saved Prompts
        </span>
      </div>

      {/* Scrollable body */}
      <div className="overflow-y-auto flex-grow-1">
        {loading ? (
          <div className={styles.loadingState}>
            <LucideIcon name="loader" size={16} />
            Loading…
          </div>
        ) : prompts.length === 0 ? (
          <div className={`d-flex flex-column align-items-center justify-content-center text-theme-secondary ${styles.emptyState}`}>
            <span className={styles.emptyStateText}>No saved prompts yet.</span>
          </div>
        ) : (
          prompts.map((p) => (
            <div key={p.id} className={styles.card}>
              <div className="flex-grow-1 min-w-0">
                <div className={styles.cardPrompt}>
                  {p.prompt || <em className={styles.cardEmptyPrompt}>empty prompt</em>}
                </div>
                {p.negative_prompt && (
                  <div className={styles.cardNegPrompt}>
                    {p.negative_prompt}
                  </div>
                )}
              </div>
              <div className={styles.cardActions}>
                <button
                  type="button"
                  onClick={() => { onLoad(p); onClose(); }}
                  title="Load this prompt"
                  className={styles.loadBtn}
                >
                  Load
                </button>
                <button
                  type="button"
                  onClick={() => handleDelete(p.id)}
                  disabled={deleting === p.id}
                  title="Delete"
                  className={styles.deleteBtn}
                  style={deleting === p.id ? { opacity: 0.4 } : undefined}
                >
                  <LucideIcon name="trash" size={13} />
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
