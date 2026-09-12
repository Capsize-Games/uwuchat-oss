import { EdgeOnly } from "../../../context/DeploymentContext";
import styles from "./KBRow.module.css";

export default function KBRow({
  doc,
  onToggle,
  onDragStart,
}: {
  doc: { id: number; name: string; active: boolean; indexed: boolean };
  onToggle: (docId: number) => void;
  onDragStart: (e: React.DragEvent<HTMLTableRowElement>, docId: number) => void;
}) {
  return (
    <tr
      key={doc.id}
      draggable
      onDragStart={(e) => onDragStart(e, doc.id)}
      className={styles.row}
    >
      <td
        className={`text-truncate ${styles.name}`}
        title={doc.name}
      >
        {doc.name}
      </td>
      <td className={styles.cellCenter}>
        <span
          className="cursor-pointer d-inline-block"
          onClick={() => onToggle(doc.id)}
          title={
            doc.active
              ? "Click to deactivate"
              : "Click to activate"
          }
        >
          {doc.active ? "✅" : "☐"}
        </span>
      </td>
      <EdgeOnly>
        <td className={styles.cellCenter}>
          {doc.indexed ? "✅" : "—"}
        </td>
        <td className={styles.cellCenter}>—</td>
      </EdgeOnly>
    </tr>
  );
}
