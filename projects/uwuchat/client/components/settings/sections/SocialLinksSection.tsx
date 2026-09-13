/**
 * SocialLinksSection — manage social media links on the user profile.
 *
 * Stores links in User.data.social_links as { serviceKey: username, ... }.
 */
import { useEffect, useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../../hooks/useAuth";
import { getUser, updateUser } from "../../../api/user";
import {
  ALL_SERVICES,
  CATEGORY_LABELS,
  SERVICES_BY_CATEGORY,
  SERVICES_BY_KEY,
  type SocialCategory,
  type SocialLinksMap,
  type SocialService,
} from "../../../data/socialLinks";
import ServiceIcon from "../../../data/socialIcons";
import styles from "./SocialLinksSection.module.css";

// ── Component ──────────────────────────────────────────────────────────

export default function SocialLinksSection() {
  const { t } = useTranslation();
  const { user: authUser } = useAuth();
  const [links, setLinks] = useState<SocialLinksMap>({});
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [saving, setSaving] = useState(false);

  // Load current links from User.data.social_links
  const loadLinks = useCallback(async () => {
    setLoading(true);
    try {
      const profile = await getUser();
      if (profile?.data?.social_links) {
        setLinks(profile.data.social_links as SocialLinksMap);
      } else {
        setLinks({});
      }
    } catch {
      setLinks({});
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadLinks();
  }, [loadLinks]);

  // Persist the links map to User.data
  const saveLinks = useCallback(
    async (newLinks: SocialLinksMap) => {
      setSaving(true);
      try {
        // Preserve any existing data keys other than social_links
        const profile = await getUser();
        const existingData = (profile?.data ?? {}) as Record<string, unknown>;
        await updateUser({
          data: { ...existingData, social_links: newLinks },
        });
        setLinks(newLinks);
      } catch {
        // Revert on failure
      } finally {
        setSaving(false);
      }
    },
    [],
  );

  // Start editing a service
  const startEdit = (key: string) => {
    setEditing(key);
    setEditValue(links[key] ?? "");
  };

  // Save the edited value
  const handleSave = async () => {
    if (!editing) return;
    const trimmed = editValue.trim();
    const newLinks = { ...links };
    if (trimmed) {
      newLinks[editing] = trimmed;
    } else {
      delete newLinks[editing];
    }
    await saveLinks(newLinks);
    setEditing(null);
  };

  // Remove a link
  const handleRemove = async (key: string) => {
    const newLinks = { ...links };
    delete newLinks[key];
    await saveLinks(newLinks);
  };

  // Add a new service
  const handleAddService = async (serviceKey: string) => {
    // Open the editor for this service
    setEditing(serviceKey);
    setEditValue("");
  };

  // Cancel editing
  const handleCancelEdit = () => {
    setEditing(null);
    setEditValue("");
  };

  // Services that already have links
  const linkedKeys = new Set(Object.keys(links));

  // Services available to add (not yet linked)
  const availableServices = ALL_SERVICES.filter(
    (s) => !linkedKeys.has(s.key),
  );

  if (!authUser) {
    return (
      <div className={styles.signIn}>
        {t("settings.social_links.sign_in")}
      </div>
    );
  }

  return (
    <div>
      <h6
        className={`text-uppercase small mb-3 ${styles.heading}`}
      >
        {t("settings.social_links.heading")}
      </h6>

      <p className={`${styles.desc} small mb-4`}>
        {t("settings.social_links.desc")}
      </p>

      {loading && (
        <div className={styles.loadingText}>
          {t("common.loading")}
        </div>
      )}

      {!loading && linkedKeys.size === 0 && (
        <div className={styles.emptyState}>
          <div className={styles.emptyIcon}>🔗</div>
          <div className={styles.emptyText}>
            {t("settings.social_links.no_links")}
          </div>
        </div>
      )}

      {/* ── Existing Links ── */}
      {!loading && linkedKeys.size > 0 && (
        <div className={styles.linksList}>
          {Object.entries(links).map(([key, value]) => {
            const service = SERVICES_BY_KEY[key];
            if (!service) return null;
            const isEditing = editing === key;

            return (
              <div key={key} className={styles.linkRow}>
                {/* Service badge */}
                <div className={styles.linkService}>
                  <ServiceIcon serviceKey={service.key} size={18} />
                  <span className={styles.linkServiceLabel}>
                    {service.label}
                  </span>
                </div>

                {/* Value / Editor */}
                {isEditing ? (
                  <div className={styles.linkEdit}>
                    <input
                      type="text"
                      value={editValue}
                      onChange={(e) => setEditValue(e.target.value)}
                      placeholder={`${service.label} username or URL`}
                      autoFocus
                      className={styles.editInput}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") handleSave();
                        if (e.key === "Escape") handleCancelEdit();
                      }}
                    />
                    <button
                      onClick={handleSave}
                      disabled={saving}
                      className={styles.saveBtn}
                    >
                      {saving ? "..." : t("common.save")}
                    </button>
                    <button
                      onClick={handleCancelEdit}
                      className={styles.cancelBtn}
                    >
                      ✕
                    </button>
                  </div>
                ) : (
                  <>
                    <span className={styles.linkValue}>
                      {value}
                    </span>
                    <button
                      onClick={() => startEdit(key)}
                      className={styles.editBtn}
                    >
                      {t("settings.social_links.edit")}
                    </button>
                    <button
                      onClick={() => handleRemove(key)}
                      className={styles.removeBtn}
                    >
                      ✕
                    </button>
                  </>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* ── Add New Service ── */}
      {!loading && (
        <AddServiceDropdown
          services={availableServices}
          onSelect={handleAddService}
          t={t}
        />
      )}
    </div>
  );
}

// ── Add Service Dropdown ────────────────────────────────────────────────

function AddServiceDropdown({
  services,
  onSelect,
  t,
}: {
  services: SocialService[];
  onSelect: (key: string) => void;
  t: (key: string) => string;
}) {
  const [open, setOpen] = useState(false);

  if (services.length === 0) {
    return (
      <div className={styles.allAdded}>
        {t("settings.social_links.all_added")}
      </div>
    );
  }

  // Group remaining services by category
  const grouped: Partial<Record<SocialCategory, SocialService[]>> = {};
  for (const s of services) {
    if (!grouped[s.category]) grouped[s.category] = [];
    grouped[s.category]!.push(s);
  }

  return (
    <div className={styles.addWrapper}>
      <button
        onClick={() => setOpen(!open)}
        className={styles.addBtn}
      >
        <span className={styles.addBtnIcon}>+</span>
        {t("settings.social_links.add_link")}
      </button>

      {open && (
        <>
          {/* Backdrop to close */}
          <div
            onClick={() => setOpen(false)}
            className={styles.backdrop}
          />
          <div className={styles.dropdown}>
            {Object.entries(grouped).map(([category, svcs]) => (
              <div key={category}>
                <div className={styles.dropdownCategory}>
                  {CATEGORY_LABELS[category as SocialCategory]}
                </div>
                {svcs.map((s) => (
                  <button
                    key={s.key}
                    onClick={() => {
                      onSelect(s.key);
                      setOpen(false);
                    }}
                    className={styles.dropdownItem}
                    onMouseEnter={(e) => {
                      (e.currentTarget as HTMLElement).style.background =
                        "rgba(255,255,255,0.06)";
                    }}
                    onMouseLeave={(e) => {
                      (e.currentTarget as HTMLElement).style.background =
                        "transparent";
                    }}
                  >
                    <ServiceIcon serviceKey={s.key} size={18} />
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
