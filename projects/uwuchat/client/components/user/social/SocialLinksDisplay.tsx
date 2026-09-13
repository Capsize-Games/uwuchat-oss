import React from "react";
import { useTranslation } from "react-i18next";
import {
  ALL_SERVICES,
  SERVICES_BY_KEY,
  buildSocialUrl,
  type SocialCategory,
  type SocialLinksMap,
  type SocialService,
} from "../../../data/socialLinks";
import ServiceIcon from "../../../data/socialIcons";
import LucideIcon from "@/components/shared/LucideIcon";
import AddLinkDropdown from "./AddLinkDropdown";
import styles from "./SocialLinksDisplay.module.css";

/**
 * SocialLinkRow — a single social link row in edit/view mode.
 */
function SocialLinkRow({
  serviceKey,
  value,
  isEditing,
  isOwnProfile,
  editValue,
  saving,
  onStartEdit,
  onSaveEdit,
  onCancelEdit,
  onRemoveLink,
  onChangeEditValue,
  t,
}: {
  serviceKey: string;
  value: string;
  isEditing: boolean;
  isOwnProfile: boolean;
  editValue: string;
  saving: boolean;
  onStartEdit: (key: string) => void;
  onSaveEdit: () => void;
  onCancelEdit: () => void;
  onRemoveLink: (key: string) => void;
  onChangeEditValue: (v: string) => void;
  t: (key: string) => string;
}) {
  const service = SERVICES_BY_KEY[serviceKey];
  if (!service) return null;

  return (
    <div className={styles.linkRow}>
      <ServiceIcon serviceKey={service.key} size={18} />
      <span className={styles.linkServiceName}>
        {service.label}
      </span>

      {isEditing ? (
        <>
          <input
            type="text"
            value={editValue}
            onChange={(e) => onChangeEditValue(e.target.value)}
            placeholder={t("user.social_links.username_placeholder")}
            autoFocus
            className={styles.editInput}
            onKeyDown={(e) => {
              if (e.key === "Enter") onSaveEdit();
              if (e.key === "Escape") onCancelEdit();
            }}
          />
          <button
            onClick={onSaveEdit}
            disabled={saving}
            title="Save"
            className={styles.iconBtnSave}
          >
            <LucideIcon name="check" size={14} />
          </button>
          <button
            onClick={onCancelEdit}
            title="Cancel"
            className={styles.iconBtnCancel}
          >
            <LucideIcon name="circle-x" size={14} />
          </button>
        </>
      ) : (
        <>
          <span className={styles.linkValue}>
            {value}
          </span>
          {isOwnProfile && (
            <>
              <button
                onClick={() => onStartEdit(serviceKey)}
                title="Edit"
                className={styles.iconBtnEdit}
              >
                <LucideIcon name="square-pen" size={14} />
              </button>
              <button
                onClick={() => onRemoveLink(serviceKey)}
                title="Remove"
                className={styles.iconBtnRemove}
              >
                <LucideIcon name="trash-2" size={14} />
              </button>
            </>
          )}
        </>
      )}
    </div>
  );
}

// ── SocialLinksDisplay ────────────────────────────────────────────────

interface SocialLinksDisplayProps {
  socialLinks: SocialLinksMap;
  isOwnProfile: boolean;
  /** When true, left-align icon badges instead of centering */
  compact?: boolean;
  editingLinks: boolean;
  editingKey: string | null;
  editValue: string;
  saving: boolean;
  onToggleEdit: () => void;
  onStartEdit: (key: string) => void;
  onSaveEdit: () => void;
  onCancelEdit: () => void;
  onRemoveLink: (key: string) => void;
  onAddLink: (key: string) => void;
  onChangeEditValue: (v: string) => void;
}

/**
 * SocialLinksDisplay — renders social link badges in view mode and an
 * inline editor in edit mode (used by both the page and panel).
 */
export default function SocialLinksDisplay(
  props: SocialLinksDisplayProps,
) {
  const {
    socialLinks,
    isOwnProfile,
    compact = false,
    editingLinks,
    editingKey,
    editValue,
    saving,
    onToggleEdit,
    onStartEdit,
    onSaveEdit,
    onCancelEdit,
    onRemoveLink,
    onAddLink,
    onChangeEditValue,
  } = props;

  const { t } = useTranslation();
  const linkedKeys = new Set(Object.keys(socialLinks));
  const hasLinks = linkedKeys.size > 0;

  // ── View mode ──────────────────────────────────────────────────
  if (!editingLinks) {
    if (!hasLinks && isOwnProfile) {
      return (
        <div className={styles.emptyStateWrap}>
          <button
            onClick={onToggleEdit}
            className={styles.emptyStateBtn}
          >
            {t("user.social_links.add_links")}
          </button>
        </div>
      );
    }
    if (!hasLinks) return null;

    const gridClass = compact
      ? styles.badgeGridLeft
      : styles.badgeGridCenter;

    return (
      <div className={styles.viewWrap}>
        <div className={gridClass}>
          {Object.entries(socialLinks).map(([key, value]) => {
            const service = SERVICES_BY_KEY[key];
            if (!service || !value) return null;
            const url = buildSocialUrl(service, value);
            return (
              <a
                key={key}
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                title={service.label}
                className={styles.badgeLink}
                // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
                style={{
                  background: service.color,
                }}
              >
                <ServiceIcon serviceKey={service.key} size={16} />
              </a>
            );
          })}
          {isOwnProfile && (
            <button
              onClick={onToggleEdit}
              title={t("user.social_links.edit_links")}
              className={styles.editBadgeBtn}
            >
              <LucideIcon name="wrench" size={16} />
            </button>
          )}
        </div>
      </div>
    );
  }

  // ── Edit mode ──────────────────────────────────────────────────
  const availableServices = ALL_SERVICES.filter(
    (s) => !linkedKeys.has(s.key) && s.key !== editingKey,
  );

  const grouped: Partial<Record<SocialCategory, SocialService[]>> = {};
  for (const s of availableServices) {
    if (!grouped[s.category]) grouped[s.category] = [];
    grouped[s.category]!.push(s);
  }

  return (
    <div className={styles.editWrap}>
      <div className={styles.editHeader}>
        <span className={styles.editTitle}>
          {t("user.social_links.edit_links")}
        </span>
        <button
          onClick={onToggleEdit}
          className={styles.doneBtn}
        >
          {t("user.social_links.done")}
        </button>
      </div>

      {/* Existing links */}
      {hasLinks && (
        <div className={styles.existingLinks}>
          {Object.entries(socialLinks).map(([key, value]) => {
            const displayValue = typeof value === "string" ? value : "";
            return (
            <SocialLinkRow
              key={key}
              serviceKey={key}
              value={displayValue}
              isEditing={editingKey === key}
              isOwnProfile={isOwnProfile}
              editValue={editValue}
              saving={saving}
              onStartEdit={onStartEdit}
              onSaveEdit={onSaveEdit}
              onCancelEdit={onCancelEdit}
              onRemoveLink={onRemoveLink}
              onChangeEditValue={onChangeEditValue}
              t={t}
            />
            );
          })}
        </div>
      )}

      {/* New service being added */}
      {editingKey &&
        !linkedKeys.has(editingKey) &&
        SERVICES_BY_KEY[editingKey] && (
          <SocialLinkRow
            serviceKey={editingKey}
            value={editValue}
            isEditing={true}
            isOwnProfile={isOwnProfile}
            editValue={editValue}
            saving={saving}
            onStartEdit={onStartEdit}
            onSaveEdit={onSaveEdit}
            onCancelEdit={onCancelEdit}
            onRemoveLink={onRemoveLink}
            onChangeEditValue={onChangeEditValue}
            t={t}
          />
        )}

      {/* Add new link dropdown */}
      {availableServices.length > 0 ? (
        <AddLinkDropdown grouped={grouped} onSelect={onAddLink} />
      ) : (
        <div className={styles.allDone}>
          {t("user.social_links.all_added")}
        </div>
      )}
    </div>
  );
}
