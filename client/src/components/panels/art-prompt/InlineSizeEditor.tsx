import styles from "./InlineSizeEditor.module.css";

export default function InlineSizeEditor({
  w,
  h,
  onWChange,
  onHChange,
  onClose,
}: {
  w: number;
  h: number;
  onWChange: (v: number) => void;
  onHChange: (v: number) => void;
  onClose: () => void;
}) {
  return (
    <div className={styles.wrap}>
      <span className={styles.label}>W</span>
      <input
        type="number"
        className={`art-no-spin ${styles.input}`}
        defaultValue={w}
        onBlur={(e) => {
          const v = Math.max(64, Math.min(2048, Number(e.target.value)));
          if (!isNaN(v)) onWChange(v);
          onClose();
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            const v = Math.max(
              64,
              Math.min(2048, Number((e.target as HTMLInputElement).value)),
            );
            if (!isNaN(v)) {
              onWChange(v);
              onClose();
            }
          }
        }}
        autoFocus
      />
      <span className={styles.label}>H</span>
      <input
        type="number"
        className={`art-no-spin ${styles.input}`}
        defaultValue={h}
        onBlur={(e) => {
          const v = Math.max(64, Math.min(2048, Number(e.target.value)));
          if (!isNaN(v)) onHChange(v);
          onClose();
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            const v = Math.max(
              64,
              Math.min(2048, Number((e.target as HTMLInputElement).value)),
            );
            if (!isNaN(v)) {
              onHChange(v);
              onClose();
            }
          }
        }}
      />
    </div>
  );
}
