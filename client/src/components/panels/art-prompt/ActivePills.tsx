import styles from "./ActivePills.module.css";

interface ActivePill {
  id: number;
  name: string;
}

export function EmbeddingPills({
  embeddings,
  onDeactivate,
}: {
  embeddings: ActivePill[];
  onDeactivate: (id: number) => void;
}) {
  if (embeddings.length === 0) return null;

  return (
    <div className={`mb-1 p-2 rounded ${styles.pillGroup}`}>
      <small className={styles.pillLabel}>Active Embeddings</small>
      <div className="d-flex flex-wrap gap-1">
        {embeddings.map((emb) => (
          <span key={emb.id} className={styles.pill}>
            <span
              className={styles.pillClose}
              onClick={() => onDeactivate(emb.id)}
              title="Deactivate embedding"
            >
              ✕
            </span>
            {emb.name}
          </span>
        ))}
      </div>
    </div>
  );
}

export function LoraPills({
  loras,
  onDeactivate,
}: {
  loras: ActivePill[];
  onDeactivate: (id: number) => void;
}) {
  if (loras.length === 0) return null;

  return (
    <div className={`mb-1 p-2 rounded ${styles.pillGroupLora}`}>
      <small className={styles.pillLabelLora}>Active LoRA</small>
      <div className="d-flex flex-wrap gap-1">
        {loras.map((lora) => (
          <span key={lora.id} className={styles.pillLora}>
            <span
              className={styles.pillClose}
              onClick={() => onDeactivate(lora.id)}
              title="Deactivate LoRA"
            >
              ✕
            </span>
            {lora.name}
          </span>
        ))}
      </div>
    </div>
  );
}
