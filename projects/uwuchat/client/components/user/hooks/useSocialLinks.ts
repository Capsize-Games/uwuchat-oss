import { useState, useCallback, useEffect } from "react";
import { getUser, updateUser } from "../../../api/user";
import type { SocialLinksMap } from "../../../data/socialLinks";

/**
 * useSocialLinks — loads and manages social links, avatar, banner, and
 * status message from the user profile. Shared between UserProfilePage
 * and UserProfilePanel.
 */
export function useSocialLinks() {
  const [loading, setLoading] = useState(true);
  const [socialLinks, setSocialLinks] = useState<SocialLinksMap>({});
  const [avatarImage, setAvatarImage] = useState<string | null>(null);
  const [bannerImage, setBannerImage] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState("");
  const [kaomoji, setKaomoji] = useState("");
  const [gender, setGender] = useState<string | null>(null);
  const [countryCode, setCountryCode] = useState<string | null>(null);
  const [editingLinks, setEditingLinks] = useState(false);
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const profile = await getUser();
        if (cancelled) return;
        const links = profile?.data?.social_links;
        if (links && typeof links === "object") {
          setSocialLinks(links as SocialLinksMap);
        }
        setAvatarImage(profile?.avatar_image ?? null);
        setBannerImage(profile?.banner_image ?? null);
        const data = (profile?.data ?? {}) as Record<string, unknown>;
        setStatusMessage(
          typeof data.status_message === "string"
            ? data.status_message
            : "",
        );
        setKaomoji(
          typeof data.kaomoji === "string"
            ? data.kaomoji
            : "",
        );
        setGender(
          typeof profile?.gender === "string"
            ? profile.gender
            : null,
        );
        setCountryCode(
          typeof data.country_code === "string"
            ? data.country_code
            : null,
        );
      } catch {
        /* ignore */
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const saveLinks = useCallback(async (newLinks: SocialLinksMap) => {
    setSaving(true);
    try {
      const profile = await getUser();
      const existingData = (profile?.data ?? {}) as Record<string, unknown>;
      await updateUser({
        data: { ...existingData, social_links: newLinks },
      });
      setSocialLinks(newLinks);
    } catch {
      /* revert */
    } finally {
      setSaving(false);
    }
  }, []);

  const startEdit = (key: string) => {
    setEditingKey(key);
    setEditValue(socialLinks[key] ?? "");
  };

  const saveEdit = async () => {
    if (!editingKey) return;
    const trimmed = editValue.trim();
    const newLinks = { ...socialLinks };
    if (trimmed) {
      newLinks[editingKey] = trimmed;
    } else {
      delete newLinks[editingKey];
    }
    await saveLinks(newLinks);
    setEditingKey(null);
  };

  const removeLink = async (key: string) => {
    const newLinks = { ...socialLinks };
    delete newLinks[key];
    await saveLinks(newLinks);
  };

  const addLink = (serviceKey: string) => {
    setEditingKey(serviceKey);
    setEditValue("");
  };

  const cancelEdit = () => setEditingKey(null);
  const toggleEdit = () => {
    setEditingLinks(!editingLinks);
    setEditingKey(null);
  };

  const saveKaomoji = useCallback(async (value: string) => {
    setSaving(true);
    try {
      const profile = await getUser();
      const existingData = (profile?.data ?? {}) as Record<string, unknown>;
      await updateUser({
        data: { ...existingData, kaomoji: value },
      });
      setKaomoji(value);
    } catch {
      /* revert */
    } finally {
      setSaving(false);
    }
  }, []);

  return {
    loading,
    socialLinks,
    avatarImage,
    bannerImage,
    statusMessage,
    kaomoji,
    gender,
    countryCode,
    editingLinks,
    editingKey,
    editValue,
    saving,
    setAvatarImage,
    setBannerImage,
    setStatusMessage,
    setKaomoji,
    setEditValue,
    saveKaomoji,
    startEdit,
    saveEdit,
    cancelEdit,
    removeLink,
    addLink,
    toggleEdit,
  };
}
