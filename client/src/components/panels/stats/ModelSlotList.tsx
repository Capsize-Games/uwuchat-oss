import type { ActiveModelInfo } from "../../../api/client";
import LucideIcon from "../../shared/LucideIcon";
import type { ModelSlot } from "./useStatsPanel";
import styles from "./ModelSlotList.module.css";

interface Props {
  slots: ModelSlot[];
  loadingRef: React.MutableRefObject<Set<string>>;
  unloadingSlots: Set<string>;
  findModel: (type: string) => ActiveModelInfo | undefined;
  statusColor: (status: string) => string;
  onLoad: (type: string, id: string) => void;
  onUnload: (m: ActiveModelInfo, slotType: string) => void;
}

export default function ModelSlotList({
  slots, loadingRef, unloadingSlots, findModel, statusColor, onLoad, onUnload,
}: Props) {
  return (
    <div className="mt-2">
      <small className="text-muted d-block mb-1">Models</small>
      {slots.map(({ type, label, name, canLoad }) => {
        const m = findModel(type);
        const isUnloading = unloadingSlots.has(type) || m?.status === "unloading";
        const status = isUnloading ? "unloading" : (m?.status ?? "unloaded");
        return (
          <div
            key={type}
            className={`d-flex align-items-center justify-content-between mb-1 ${styles.row}`}
          >
            <span className={`text-truncate ${styles.name}`}>
              <span
                className={styles.statusDot}
                // eslint-disable-next-line no-restricted-syntax -- lookup-table color from shared constants
                style={{ backgroundColor: statusColor(status) }}
              />
              {label}: {name || "none"}
            </span>
            {status === "loading" || status === "unloading" || (status !== "loaded" && loadingRef.current.has(type)) ? (
              <span className={styles.loading}>
                <LucideIcon name="loader" size={14} />
              </span>
            ) : m?.can_unload ? (
              <button className="model-action-btn" onClick={() => onUnload(m, type)} title={`Unload ${label}`}>
                <LucideIcon name="octagon-alert" size={14} />
              </button>
            ) : canLoad ? (
              <button className="model-action-btn" onClick={() => onLoad(type, name)} title={`Load ${label}`}>
                <LucideIcon name="play" size={14} />
              </button>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
