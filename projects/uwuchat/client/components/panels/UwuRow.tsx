import { useTranslation } from "react-i18next";
import LucideIcon from "@/components/shared/LucideIcon";
import { getSpeciesBadge, getGenderBadge } from "../../utils/speciesIcon";
import styles from "./UwuRow.module.css";

interface UwuRecord { id: number; botname: string; name: string; avatar_emoji?: string; avatar_image?: string | null; species_data?: { type?: string; subtype?: string } | null; gender?: string | null; is_online?: boolean; has_blocked_user?: boolean; blocked_by_user?: boolean; is_deceased?: boolean; death_reason?: string | null; is_system_bot?: boolean; }
export type { UwuRecord };

export default function UwuRow({ u, isActive, confirming, previewText, onSelect, onRequestRemove, onCancelRemove, onConfirmRemove }: {
  u: UwuRecord; isActive: boolean; confirming: boolean; previewText?: string;
  onSelect: () => void; onRequestRemove: (e: React.MouseEvent) => void;
  onCancelRemove: (e: React.MouseEvent) => void; onConfirmRemove: (e: React.MouseEvent) => void;
}) {
  const { t } = useTranslation();
  const deceased = u.is_deceased === true;
  const isSystem = u.is_system_bot === true;
  const speciesBadge = getSpeciesBadge(u.species_data?.type, u.species_data?.subtype);
  const genderBadge = getGenderBadge(u.gender);

  const rowCls = deceased ? styles.rowDeceased : isActive ? styles.rowActive : styles.rowInactive;
  const avatarCls = isActive ? styles.avatarActive : styles.avatarInactive;
  const nameCls = deceased ? styles.nameDeceased : isActive ? styles.nameActive : styles.nameInactive;
  const badgeRowCls = deceased ? styles.badgeRowDeceased : styles.badgeRow;

  return (
    <div onClick={onSelect} title={deceased && u.death_reason ? u.death_reason : undefined} className={rowCls}>
      <div className={styles.avatarWrap}>
        {/* eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation */}
        <div className={avatarCls} style={{ filter: deceased ? "grayscale(1)" : undefined }}>
          {u.avatar_image ? <img src={`data:image/png;base64,${u.avatar_image}`} alt="" className={styles.avatarImg} /> : u.avatar_emoji || "🤖"}
        </div>
        {deceased && <span title="Deceased" className={styles.deceasedDot} />}
      </div>
      <div className={styles.info}>
        <div className={styles.nameRow}>
          <div className={nameCls}>{u.botname || u.name || `UwU ${u.id}`}</div>
        </div>
        {(speciesBadge || genderBadge) && (
          <div className={badgeRowCls}>
            {speciesBadge && <span title={speciesBadge.label} className="d-flex align-items-center flex-shrink-0"><LucideIcon name={speciesBadge.icon} size={16} /></span>}
            {genderBadge && <span title={genderBadge.label} className="d-flex align-items-center flex-shrink-0"><LucideIcon name={genderBadge.icon} size={16} /></span>}
          </div>
        )}
        {previewText && <div className={styles.preview}>{previewText}</div>}
      </div>
      {!isSystem && confirming ? (
        <div className={styles.confirmRow} onClick={(e) => e.stopPropagation()}>
          <button type="button" onClick={onConfirmRemove} className={styles.confirmYes}>{t("panels.uwu_list.remove")}</button>
          <button type="button" onClick={onCancelRemove} className={styles.confirmNo}>{t("common.cancel")}</button>
        </div>
      ) : !isSystem ? (
        <button type="button" onClick={onRequestRemove} title={t("panels.uwu_list.remove_title")} className={styles.removeBtn}><LucideIcon name="user-minus" size={13} /></button>
      ) : null}
    </div>
  );
}
