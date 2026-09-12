import CivitaiImage from "./CivitaiImage";
import styles from "./CivitaiResultCard.module.css";

interface ResultItem {
  id: number;
  name: string;
  type?: string;
  baseModel?: string;
  creator?: string;
  thumbnail?: string;
  /** Inline base64 thumbnails from the server, keyed by size. */
  thumbnails?: Record<string, string>;
}

interface CivitaiResultCardProps {
  item: ResultItem;
  selected: boolean;
  onSelect: (id: number) => void;
}

export default function CivitaiResultCard({
  item,
  selected,
  onSelect,
}: CivitaiResultCardProps) {
  const thumbBase64 = item.thumbnails?.small;
  const thumbUrl = item.thumbnail || "";
  return (
    <div
      data-model-id={item.id}
      onClick={() => onSelect(item.id)}
      className={`${styles.card} ${selected ? styles.cardSelected : styles.cardNotSelected}`}
    >
      <div className={styles.thumbBox}>
        {thumbBase64 || thumbUrl ? (
          <CivitaiImage
            url={thumbUrl}
            alt={item.name}
            width={40}
            base64={thumbBase64}
            className={styles.thumbImg}
          />
        ) : (
          <div className={styles.thumbFallback} />
        )}
      </div>
      <div className={styles.info}>
        <div className={`text-truncate ${styles.name}`}>
          {item.name}
        </div>
        <div className="text-muted text-truncate">
          {item.creator ?? "Unknown"}
        </div>
        <div className={`text-muted text-truncate ${styles.meta}`}>
          {item.type ?? ""}
          {item.baseModel ? ` · ${item.baseModel}` : ""}
        </div>
      </div>
    </div>
  );
}
