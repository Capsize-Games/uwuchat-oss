import LucideIcon from "../../../components/shared/LucideIcon";
import styles from "./CollapsedRail.module.css";

export type AssetTab = "layers" | "images";

const TABS: { id: AssetTab; icon: string; label: string }[] = [
  { id: "layers", icon: "layers", label: "Layers" },
  { id: "images", icon: "images", label: "Images" },
];

interface Props {
  activeTab: AssetTab;
  onExpand: (tab?: AssetTab) => void;
}

export default function CollapsedRail({ activeTab, onExpand }: Props) {
  return (
    <div
      className={`flex-shrink-0 d-flex flex-column align-items-center overflow-hidden ${styles.root}`}
    >
      <button className={styles.railBtn} title="Expand panel" onClick={() => onExpand()}>
        <LucideIcon name="chevron-left" size={14} />
      </button>
      <div className="sep-h" />
      {TABS.map((t) => (
        <button
          key={t.id}
          className={styles.railBtn}
          // eslint-disable-next-line no-restricted-syntax -- state-driven conditional style
          style={{ color: activeTab === t.id ? "var(--bs-primary)" : undefined }}
          title={t.label}
          onClick={() => onExpand(t.id)}
        >
          <LucideIcon name={t.icon} size={14} />
        </button>
      ))}
    </div>
  );
}
