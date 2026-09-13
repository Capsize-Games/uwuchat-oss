// ── Action Menu Item Components ─────────────────────────────────────────
import type { MouseEvent } from "react";
import LucideIcon from "../../shared/LucideIcon";
import styles from "./ActionMenuBar.module.css";
import type { ActionMenuEvent } from "./events";
import { dispatchMenuAction } from "./events";

// ── Menu data types ─────────────────────────────────────────────────────

export interface MenuAction {
  type: "action";
  label: string;
  action: ActionMenuEvent["type"];
  icon?: string;
  shortcut?: string;
  disabled?: boolean;
}

export interface MenuCheckbox {
  type: "checkbox";
  label: string;
  action: ActionMenuEvent["type"];
  checked: boolean;
  onToggle: () => void;
  disabled?: boolean;
}

export interface MenuSubmenu {
  type: "submenu";
  label: string;
  items: MenuEntry[];
}

export interface MenuDivider {
  type: "divider";
}

export type MenuEntry =
  | MenuAction
  | MenuCheckbox
  | MenuSubmenu
  | MenuDivider;

export interface MenuGroup {
  label: string;
  items: MenuEntry[];
}

// ── Subcomponents ───────────────────────────────────────────────────────

function CheckIcon({ checked }: { checked: boolean }) {
  return (
    <span className={styles.checkMark}>
      {checked ? "\u2713" : ""}
    </span>
  );
}

export function SubMenuItemRow({
  entry,
  onClose,
}: {
  entry: MenuEntry;
  onClose: () => void;
}) {
  if (entry.type === "submenu") return null;

  if (entry.type === "divider") {
    return <div className={styles.divider} />;
  }

  const isDisabled =
    "disabled" in entry ? entry.disabled : false;

  if (entry.type === "checkbox") {
    return (
      <button
        disabled={isDisabled}
        className={
          styles.checkboxItem + (isDisabled ? " " + styles.disabled : "")
        }
        onClick={() => {
          if (isDisabled) return;
          entry.onToggle();
          onClose();
        }}
      >
        <CheckIcon checked={entry.checked} />
        <span className={styles.checkboxLabel}>{entry.label}</span>
      </button>
    );
  }

  return (
    <button
      disabled={isDisabled}
      className={
        styles.menuItem + (isDisabled ? " " + styles.disabled : "")
      }
      onClick={() => {
        if (isDisabled) return;
        dispatchMenuAction({ type: entry.action });
        onClose();
      }}
    >
      <span className={styles.iconWrap}>
        {entry.icon && (
          <LucideIcon
            name={entry.icon}
            size={13}
            className="text-theme-secondary"
          />
        )}
        <span>{entry.label}</span>
      </span>
      {entry.shortcut && (
        <span className={styles.shortcut}>
          {entry.shortcut}
        </span>
      )}
    </button>
  );
}

export function MenuItemRow({
  entry,
  onClose,
  onHover,
  hoveredSub,
}: {
  entry: MenuEntry;
  onClose: () => void;
  onHover: (label: string | null) => void;
  hoveredSub: string | null;
}) {
  if (entry.type === "divider") {
    return <div className={styles.divider} />;
  }

  if (entry.type === "submenu") {
    const open = hoveredSub === entry.label;
    return (
      <div
        className={
          styles.menuItem + " " + styles.menuWrapper + " " + (open ? styles.menuBtnActive : "")
        }
        onMouseEnter={() => onHover(entry.label)}
        onMouseLeave={() => onHover(null)}
      >
        <span>{entry.label}</span>
        <span className={styles.submenuArrow}>&#9654;</span>
        {open && (
          <div className={styles.submenuWrapper}>
            {entry.items.map((child, ci) => (
              <SubMenuItemRow
                key={ci}
                entry={child}
                onClose={onClose}
              />
            ))}
          </div>
        )}
      </div>
    );
  }

  return <SubMenuItemRow entry={entry} onClose={onClose} />;
}
