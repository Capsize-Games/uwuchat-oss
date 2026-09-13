/**
 * UserProfilePanel — user profile shown in the right sidebar panel.
 *
 * Orchestrates avatar/status/description editing, social links,
 * and Bluesky feed via extracted sub-components.
 */
import React, { useEffect, useRef, useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { Link2, MessageSquareText, Gamepad2 } from "lucide-react";
import { useAuth } from "../../hooks/useAuth";
import { useUserSetup } from "../../hooks/useUserSetup";
import { useBlueskyProfile } from "../../hooks/useBlueskyProfile";
import { getUser, updateUser } from "../../api/user";
import { useSocialLinks } from "./hooks/useSocialLinks";
import ImageUpload from "./ImageUpload";
import SocialLinksDisplay from "./social/SocialLinksDisplay";
import PanelAvatarInfo from "./panel/PanelAvatarInfo";
import PanelMobileHeader from "./panel/PanelMobileHeader";
import PanelBlueskyTab from "./panel/PanelBlueskyTab";
import PanelSteamTab from "./panel/PanelSteamTab";
import ProfileInfoBar from "./ProfileInfoBar";
import GenderBadge from "./GenderBadge";
import PanelWeatherTab from "./panel/PanelWeatherTab";
import { useSteamProfile } from "../../hooks/useSteamProfile";
import { useItchioProfile } from "../../hooks/useItchioProfile";
import { getSteamAuthUrl } from "../../api/steam";
import { getItchAuthUrl } from "../../api/itchio";
import { useIsMobile } from "../../hooks/useIsMobile";
import styles from "./UserProfilePanel.module.css";

// ── Types ────────────────────────────────────────────────────────

type Tab = "social" | "bluesky" | "weather" | "steam";

const TAB_ICON_SIZE = 18;

// Curated banner gradients shown when the user hasn't uploaded a banner
// image, instead of a flat placeholder fill. Picked deterministically per
// user so a given profile always shows the same gradient.
const BANNER_PRESETS = [
  "linear-gradient(135deg, #6d28d9 0%, #db2777 50%, #f59e0b 100%)",
  "linear-gradient(135deg, #0891b2 0%, #6366f1 50%, #a855f7 100%)",
  "linear-gradient(135deg, #059669 0%, #0891b2 50%, #6366f1 100%)",
  "linear-gradient(135deg, #dc2626 0%, #db2777 50%, #7c3aed 100%)",
  "linear-gradient(135deg, #ea580c 0%, #dc2626 50%, #db2777 100%)",
];

function pickBannerPreset(seed: string | number | undefined | null): string {
  const s = String(seed ?? "uwu");
  let hash = 0;
  for (let i = 0; i < s.length; i++) {
    hash = (hash * 31 + s.charCodeAt(i)) >>> 0;
  }
  return BANNER_PRESETS[hash % BANNER_PRESETS.length];
}

// ── Main Component ───────────────────────────────────────────────

export default function UserProfilePanel() {
  const { t } = useTranslation();
  const { user: authUser } = useAuth();
  const { user: setupUser } = useUserSetup();
  const sl = useSocialLinks();
  const [activeTab, setActiveTab] = useState<Tab>("weather");
  const [saving, setSaving] = useState(false);

  // Panel width detection for responsive layout
  const panelRef = useRef<HTMLDivElement>(null);
  const [panelWidth, setPanelWidth] = useState(300);
  useEffect(() => {
    const el = panelRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries)
        setPanelWidth(entry.contentRect.width);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const isMobile = useIsMobile();
  const isEnlarged = !isMobile && panelWidth > 380;

  const saveField = useCallback(
    async (field: string, value: string) => {
      setSaving(true);
      try {
        const profile = await getUser();
        const existingData = (profile?.data ?? {}) as Record<string, unknown>;
        await updateUser({ data: { ...existingData, [field]: value } });
      } finally {
        setSaving(false);
      }
    },
    [],
  );

  const handleSaveStatus = useCallback(
    async (status: string) => {
      await saveField("status_message", status);
      sl.setStatusMessage(status);
    },
    [saveField, sl],
  );

  const displayName =
    setupUser?.display_name ?? authUser?.username ?? "User";

  const userId = authUser?.id ?? null;

  // Bluesky
  const {
    status: blueskyStatus,
    posts: blueskyPosts,
    postsLoading: blueskyPostsLoading,
    loading: blueskyLoading,
    refresh: blueskyRefresh,
  } = useBlueskyProfile(userId);

  // Steam
  const {
    profile: steamProfile,
    status: steamStatus,
    loading: steamLoading,
  } = useSteamProfile(userId);
  const steamConnected = steamStatus?.connected === true;

  useEffect(() => {
    if (steamConnected) {
      import("../../api/steam").then(({ refreshSteamData }) => {
        refreshSteamData().catch(() => {});
      });
    }
  }, [steamConnected]);

  // itch.io
  const {
    connected: itchConnected,
    games: itchGames,
    displayName: itchDisplayName,
    coverUrl: itchCoverUrl,
  } = useItchioProfile(userId);

  const handleConnectItch = useCallback(async () => {
    try {
      const url = await getItchAuthUrl();
      window.location.href = url;
    } catch (err) {
      console.error("itch.io connect failed:", err);
    }
  }, []);

  const handleConnectSteam = useCallback(async () => {
    try {
      const url = await getSteamAuthUrl();
      window.location.href = url;
    } catch (err) {
      console.error("Steam connect failed:", err);
    }
  }, []);

  const TABS: { id: Tab; icon: React.ReactNode; label: string }[] = [
    { id: "weather", label: t("user.profile_panel.tab_weather"), icon: <span className={styles.tabIcon}>🌤</span> },
    { id: "steam", label: t("user.profile_panel.tab_games"), icon: <Gamepad2 size={TAB_ICON_SIZE} /> },
    { id: "bluesky", label: t("user.profile_panel.tab_posts"), icon: <MessageSquareText size={TAB_ICON_SIZE} /> },
    { id: "social", label: t("user.profile_panel.tab_links"), icon: <Link2 size={TAB_ICON_SIZE} /> },
  ];

  if (sl.loading) {
    return (
      <div ref={panelRef} className={styles.panel}>
        <div className={styles.tabContentScroll}>
          <div className={styles.loadingText}>
            Loading profile…
          </div>
        </div>
      </div>
    );
  }

  return (
    <div ref={panelRef} className={styles.panel}>
      <div className={styles.headerFixed}>
        {isMobile ? (
          <PanelMobileHeader
            displayName={displayName}
            avatarImage={sl.avatarImage}
            bannerImage={sl.bannerImage}
            bannerFallback={pickBannerPreset(authUser?.id)}
            statusMessage={sl.statusMessage}
            gender={sl.gender}
            saving={saving}
            onAvatarUploaded={sl.setAvatarImage}
            onBannerUploaded={sl.setBannerImage}
            onSaveStatus={handleSaveStatus}
            kaomojiContent={
              <ProfileInfoBar
                kaomoji={sl.kaomoji}
                isOwnProfile={true}
                onSaveKaomoji={sl.saveKaomoji}
                countryCode={sl.countryCode}
              />
            }
          />
        ) : (
          <>
            {/* Banner */}
            <div
              className={styles.bannerWrap}
              // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
              style={{
                height: isEnlarged ? 180 : 100,
                background: sl.bannerImage
                  ? undefined
                  : pickBannerPreset(authUser?.id),
              }}
            >
              <ImageUpload
                imageType="banner"
                onUploaded={(b64) => sl.setBannerImage(b64)}
                // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
                style={{ width: "100%", height: "100%" }}
              >
                {sl.bannerImage ? (
                  <img
                    src={`data:image/png;base64,${sl.bannerImage}`}
                    alt="banner"
                    className={styles.bannerImg}
                  />
                ) : (
                  <div className={styles.bannerPlaceholder}>
                    {t("user.profile_panel.click_to_add_banner")}
                  </div>
                )}
              </ImageUpload>

              <div className={styles.genderBadgePos}>
                <GenderBadge gender={sl.gender} />
              </div>
            </div>

            {/* Hero — overlaps the banner */}
            <div className={styles.heroWrap}>
              <PanelAvatarInfo
                displayName={displayName}
                avatarImage={sl.avatarImage}
                statusMessage={sl.statusMessage}
                saving={saving}
                isEnlarged={isEnlarged}
                onAvatarUploaded={sl.setAvatarImage}
                onSaveStatus={handleSaveStatus}
                kaomojiContent={
                  <ProfileInfoBar
                    kaomoji={sl.kaomoji}
                    isOwnProfile={true}
                    onSaveKaomoji={sl.saveKaomoji}
                    countryCode={sl.countryCode}
                  />
                }
              />
            </div>
          </>
        )}

        {/* Tab Bar */}
        <div className={styles.tabBar}>
          {TABS.map((tab) => {
            const isActive = activeTab === tab.id;
            const btnClass = isActive
              ? styles.tabBtnActive
              : styles.tabBtnInactive;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={btnClass}
                // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
                style={{
                  gap: isEnlarged ? 5 : 0,
                  padding: isMobile
                    ? "6px 8px"
                    : isEnlarged
                      ? "8px 12px"
                      : "8px 10px",
                }}
              >
                {tab.icon}
                {isEnlarged && (
                  <span className={styles.tabLabel}>{tab.label}</span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Tab Content */}
      {activeTab === "steam" ? (
        <div className={styles.steamContent}>
          <PanelSteamTab
            steamConnected={steamConnected}
            steamLoading={steamLoading}
            steamProfile={steamProfile}
            onConnect={handleConnectSteam}
            itchConnected={itchConnected}
            itchGames={itchGames}
            itchDisplayName={itchDisplayName}
            itchCoverUrl={itchCoverUrl}
            onConnectItch={handleConnectItch}
            compact={!isEnlarged}
          />
        </div>
      ) : (
        <div className={styles.tabContentScroll}>
          <div className={styles.tabContentPad}>
            {activeTab === "social" && (
              <SocialLinksDisplay
                socialLinks={sl.socialLinks}
                isOwnProfile={true}
                compact={!isEnlarged}
                editingLinks={sl.editingLinks}
                editingKey={sl.editingKey}
                editValue={sl.editValue}
                saving={sl.saving}
                onToggleEdit={sl.toggleEdit}
                onStartEdit={sl.startEdit}
                onSaveEdit={sl.saveEdit}
                onCancelEdit={sl.cancelEdit}
                onRemoveLink={sl.removeLink}
                onAddLink={sl.addLink}
                onChangeEditValue={sl.setEditValue}
              />
            )}

            {activeTab === "weather" && <PanelWeatherTab />}

            {activeTab === "bluesky" && (
              <PanelBlueskyTab
                posts={blueskyPosts}
                postsLoading={blueskyPostsLoading}
                status={blueskyStatus}
                loading={blueskyLoading}
                userId={userId}
                onRefresh={blueskyRefresh}
              />
            )}
          </div>
        </div>
      )}
    </div>
  );
}
