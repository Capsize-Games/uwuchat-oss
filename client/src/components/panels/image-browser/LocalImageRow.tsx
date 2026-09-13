import { useState, useCallback } from "react";
import type { LocalImageEntry } from "./LocalImageHelpers";
import { formatFileSize, truncate } from "./LocalImageHelpers";
import ImageContextMenu, {
  dataUrlToBlob,
  saveBlobToDisk,
  type ContextMenuAction,
} from "./ImageContextMenu";
import styles from "./LocalImageRow.module.css";

export default function LocalImageRow({
  entry,
  onDelete,
}: {
  entry: LocalImageEntry;
  onDelete: (id: string) => void;
}) {
  const [ctxMenuPos, setCtxMenuPos] = useState<{
    x: number;
    y: number;
  } | null>(null);

  const handleContextMenu = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      setCtxMenuPos({ x: e.clientX, y: e.clientY });
    },
    [],
  );

  const handleExport = async () => {
    try {
      const blob = dataUrlToBlob(entry.dataUrl);
      await saveBlobToDisk(blob, `${entry.id}.png`);
    } catch {
      // export failed silently
    }
  };

  const actions: (ContextMenuAction | "divider")[] = [
    {
      label: "Export image",
      icon: "download",
      onClick: handleExport,
    },
    "divider",
    {
      label: "Delete",
      icon: "trash",
      onClick: () => onDelete(entry.id),
      danger: true,
    },
  ];

  return (
    <>
      <div
        key={`local-${entry.id}`}
        className={`d-flex border rounded p-1 mb-1 align-items-start ${styles.row}`}
        onContextMenu={handleContextMenu}
      >
        <div className={`border rounded overflow-hidden flex-shrink-0 ${styles.thumbnail}`}>
          <img
            src={entry.dataUrl}
            alt={entry.id}
            className={`w-100 h-100 ${styles.thumbImg}`}
            loading="lazy"
          />
        </div>

        <div className="ms-2 flex-grow-1 overflow-hidden">
          <div className="d-flex justify-content-between align-items-start">
            <strong className={`small ${styles.filename}`}>
              {entry.id}
            </strong>
            <span className="small text-muted flex-shrink-0 ms-1">
              {formatFileSize(entry.fileSize)}
            </span>
          </div>

          <div className="small text-muted">
            Stored locally · {entry.timestamp}
            <button
              className={`btn btn-link btn-sm p-0 ms-1 small text-danger ${styles.deleteLink}`}
              onClick={() => onDelete(entry.id)}
              title="Delete local image"
            >
              Delete
            </button>
          </div>

          {(entry.prompt || entry.seed || entry.steps) && (
            <div className={`small text-muted mt-1 ${styles.metaBlock}`}>
              {entry.prompt && (
                <span className="me-2">
                  <strong>prompt:</strong>{" "}
                  {truncate(entry.prompt, 40)}{" "}
                </span>
              )}
              {entry.seed !== undefined && (
                <span className="me-2">
                  <strong>seed:</strong> {entry.seed}{" "}
                </span>
              )}
              {entry.steps !== undefined && (
                <span className="me-2">
                  <strong>steps:</strong> {entry.steps}{" "}
                </span>
              )}
            </div>
          )}
        </div>
      </div>

      {ctxMenuPos && (
        <ImageContextMenu
          x={ctxMenuPos.x}
          y={ctxMenuPos.y}
          actions={actions}
          onClose={() => setCtxMenuPos(null)}
        />
      )}
    </>
  );
}
