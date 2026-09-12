import { useState } from "react";
import LucideIcon from "../../shared/LucideIcon";
import InfoItem from "./InfoItem";
import styles from "./SeedInfoRow.module.css";

interface SeedInfoRowProps {
  seed: number;
  seedRandomized: boolean;
  focusedField: string | null;
  onToggleFocused: (field: string) => void;
  onSeedChange: (v: number) => void;
  onToggleRandom: () => void;
}

export default function SeedInfoRow({
  seed,
  seedRandomized,
  focusedField,
  onToggleFocused,
  onSeedChange,
  onToggleRandom,
}: SeedInfoRowProps) {
  const [seedCopied, setSeedCopied] = useState(false);
  const editing = focusedField === "seed";

  return (
    <InfoItem
      icon="shuffle"
      label={seedRandomized ? "Seed (random)" : "Seed (fixed)"}
      dimmed={seedRandomized}
      editing={editing}
      onClick={() => onToggleFocused("seed")}
      editor={
        <div className={styles.editorWrap}>
          <input
            type="number" className={`art-no-spin ${styles.seedInput}`} value={seed}
            onChange={(e) => {
              const v = Number(e.target.value);
              if (!isNaN(v)) onSeedChange(v);
            }}
          />
        </div>
      }
    >
      <div className={styles.actionRow}>
        {!editing && (
          <span className={seedRandomized ? styles.seedValueDimmed : styles.seedValue}>
            {String(seed)}
          </span>
        )}
        {!editing && (
          <button type="button"
            title={seedRandomized ? "Seed: switch to fixed" : "Seed: switch to random"}
            onClick={(e) => { e.stopPropagation(); onToggleRandom(); }}
            className={seedRandomized ? styles.miniBtnActive : styles.miniBtn}
          >
            <LucideIcon name="shuffle" size={10} />
          </button>
        )}
        {!editing && (
          <button type="button"
            title={seedCopied ? "Copied!" : "Copy seed to clipboard"}
            onClick={(e) => {
              e.stopPropagation();
              navigator.clipboard.writeText(String(seed));
              setSeedCopied(true);
              setTimeout(() => setSeedCopied(false), 1500);
            }}
            className={seedCopied ? styles.miniBtnActive : styles.miniBtn}
          >
            <LucideIcon name={seedCopied ? "check" : "copy"} size={10} />
          </button>
        )}
      </div>
    </InfoItem>
  );
}
