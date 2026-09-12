import styles from "./ActiveDocPills.module.css";

interface ActiveDoc {
  id: number;
  name: string;
}

export default function ActiveDocPills({
  activeDocs,
  onRemoveDoc,
}: {
  activeDocs: ActiveDoc[];
  onRemoveDoc: (id: number) => void;
}) {
  if (activeDocs.length === 0) return null;

  return (
    <div className="d-flex flex-wrap gap-1">
      {activeDocs.map((doc) => (
        <span key={doc.id} className={styles.pill}>
          <span
            className={styles.removeBtn}
            onClick={() => onRemoveDoc(doc.id)}
            title="Remove from RAG"
          >
            ✕
          </span>
          {doc.name}
        </span>
      ))}
    </div>
  );
}
