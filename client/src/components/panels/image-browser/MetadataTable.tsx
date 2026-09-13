import type { ImageInfo } from "../../../api/client";
import styles from "./MetadataTable.module.css";

function filterMetadata(img: ImageInfo): [string, unknown][] {
  const version = img.metadata?.version as string | undefined;
  const versionStr = typeof version === "string" ? version.toLowerCase() : "";
  const isSdxlVersion =
    versionStr.includes("sdxl") ||
    versionStr.includes("hyper") ||
    versionStr.includes("lightning");
  const hiddenKeys = [
    "prompt_2", "negative_prompt", "negative_prompt_2",
    "secondary_prompt", "secondary_negative_prompt",
  ];
  return img.metadata
    ? Object.entries(img.metadata).filter(([key]) => isSdxlVersion || !hiddenKeys.includes(key))
    : [];
}

export default function MetadataTable({ img }: { img: ImageInfo }) {
  const metaEntries = filterMetadata(img);

  if (metaEntries.length === 0) {
    return <p className={styles.empty}>No metadata</p>;
  }

  return (
    <table className={styles.table}>
      <thead>
        <tr className={styles.headerRow}>
          <th className={styles.th}>Metadata</th>
          <th className={styles.thRight} />
        </tr>
      </thead>
      <tbody>
        {metaEntries.map(([key, value], idx) => {
          const valStr = typeof value === "object" ? JSON.stringify(value) : String(value);
          return (
            <tr key={key} className={idx % 2 === 0 ? styles.rowEven : styles.rowOdd}>
              <td className={styles.tdKey}>{key}</td>
              <td className={styles.tdValue} title={valStr}>
                {valStr.length > 120 ? valStr.slice(0, 120) + "..." : valStr}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
