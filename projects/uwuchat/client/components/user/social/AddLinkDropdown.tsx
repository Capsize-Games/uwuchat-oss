import React from "react";
import {
  CATEGORY_LABELS,
  type SocialCategory,
  type SocialService,
} from "../../../data/socialLinks";
import ServiceIcon from "../../../data/socialIcons";
import styles from "./AddLinkDropdown.module.css";

export default function AddLinkDropdown({
  grouped,
  onSelect,
}: {
  grouped: Partial<Record<SocialCategory, SocialService[]>>;
  onSelect: (key: string) => void;
}) {
  const [open, setOpen] = React.useState(false);

  return (
    <div className={styles.wrap}>
      <button
        onClick={() => setOpen(!open)}
        className={styles.trigger}
      >
        <span>+</span> Add a link
      </button>

      {open && (
        <>
          <div
            onClick={() => setOpen(false)}
            className={styles.backdrop}
          />
          <div className={styles.dropdown}>
            {Object.entries(grouped).map(([category, svcs]) => (
              <div key={category}>
                <div className={styles.catLabel}>
                  {CATEGORY_LABELS[category as SocialCategory]}
                </div>
                {svcs.map((s) => (
                  <button
                    key={s.key}
                    onClick={() => {
                      onSelect(s.key);
                      setOpen(false);
                    }}
                    className={styles.itemBtn}
                  >
                    <ServiceIcon serviceKey={s.key} size={16} />
                    {s.label}
                  </button>
                ))}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
