import { useEffect, useRef, useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { MapPin } from "lucide-react";
import {
  getUser,
  updateUser,
  geocodeCity,
  reverseGeocode,
} from "../../../api/user";
import { SettingsButton } from "../SettingsButton";
import { Toggle } from "../../ui/Toggle";
import styles from "./LocationSection.module.css";

const MIN_SAVE_INTERVAL_MS = 300_000; // 5 minutes
const MIN_MOVE_M = 1000; // ~1 km

function haversineMeters(
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number,
): number {
  const R = 6_371_000;
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

export default function LocationSection() {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [cityInput, setCityInput] = useState("");
  const [countryInput, setCountryInput] = useState("");
  const [geoStatus, setGeoStatus] = useState<string | null>(null);
  const [displayName, setDisplayName] = useState<string | null>(null);
  const [autoUpdate, setAutoUpdate] = useState(false);
  const watchIdRef = useRef<number | null>(null);
  const lastSaveRef = useRef<number>(0);
  const lastCoordsRef = useRef<{ lat: number; lon: number } | null>(null);

  useEffect(() => {
    getUser()
      .then((profile) => {
        const d = (profile?.data ?? {}) as Record<string, unknown>;
        if (d.location_display_name)
          setDisplayName(d.location_display_name as string);
        if (d.location_auto_update === true) setAutoUpdate(true);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  // ── Persist autoUpdate in account data blob ──────────────────────────
  const persistAutoUpdate = useCallback(
    async (enabled: boolean) => {
      try {
        const profile = await getUser();
        const d = ((profile?.data ?? {}) as Record<string, unknown>);
        await updateUser({
          data: {
            ...d,
            location_auto_update: enabled,
          },
        });
      } catch {
        /* ignore */
      }
    },
    [],
  );

  // ── Geolocation watch ────────────────────────────────────────────────
  useEffect(() => {
    if (!autoUpdate || !navigator.geolocation) return;

    const onPosition = async (pos: GeolocationPosition) => {
      const { latitude, longitude } = pos.coords;
      const now = Date.now();

      // Throttle: skip if less than 5 min since last save
      if (now - lastSaveRef.current < MIN_SAVE_INTERVAL_MS) return;

      // Throttle: skip if coordinates haven't moved ~1 km
      if (lastCoordsRef.current) {
        const dist = haversineMeters(
          lastCoordsRef.current.lat,
          lastCoordsRef.current.lon,
          latitude,
          longitude,
        );
        if (dist < MIN_MOVE_M) return;
      }

      lastCoordsRef.current = { lat: latitude, lon: longitude };
      lastSaveRef.current = now;

      // Reverse geocode
      const result = await reverseGeocode(latitude, longitude);
      const name = result?.display_name ?? `${latitude.toFixed(4)}, ${longitude.toFixed(4)}`;
      setDisplayName(name);
      setGeoStatus("✓ " + t("settings.location.saved"));

      // Save to server
      setSaving(true);
      try {
        const profile = await getUser();
        const d = ((profile?.data ?? {}) as Record<string, unknown>);
        await updateUser({
          data: {
            ...d,
            latitude,
            longitude,
            location_display_name: name,
            location_auto_update: true,
          },
        });
      } catch {
        /* ignore */
      } finally {
        setSaving(false);
      }
    };

    const onError = () => {
      setGeoStatus(t("settings.location.blocked"));
    };

    watchIdRef.current = navigator.geolocation.watchPosition(
      onPosition,
      onError,
      { enableHighAccuracy: false, maximumAge: 60_000 },
    );

    return () => {
      if (watchIdRef.current !== null) {
        navigator.geolocation.clearWatch(watchIdRef.current);
        watchIdRef.current = null;
      }
    };
  }, [autoUpdate, t]);

  // ── Toggle auto-update ───────────────────────────────────────────────
  const handleToggleAuto = useCallback(
    (enabled: boolean) => {
      setAutoUpdate(enabled);
      if (!enabled && watchIdRef.current !== null) {
        navigator.geolocation.clearWatch(watchIdRef.current);
        watchIdRef.current = null;
        lastCoordsRef.current = null;
      }
      void persistAutoUpdate(enabled);
    },
    [persistAutoUpdate],
  );

  const handleSave = async (
    latitude: number,
    longitude: number,
    name: string,
  ) => {
    setSaving(true);
    try {
      const profile = await getUser();
      const d = ((profile?.data ?? {}) as Record<string, unknown>);
      await updateUser({
        data: { ...d, latitude, longitude, location_display_name: name },
      });
    } catch {
      /* ignore */
    } finally {
      setSaving(false);
    }
  };

  const handleOneShotBrowser = useCallback(() => {
    if (!navigator.geolocation) {
      setGeoStatus(t("settings.location.not_available"));
      return;
    }
    setGeoStatus(t("settings.location.detecting"));
    navigator.geolocation.getCurrentPosition(async (pos) => {
      const { latitude, longitude } = pos.coords;
      // Try reverse geocoding
      const result = await reverseGeocode(latitude, longitude);
      const name =
        result?.display_name ??
        `${latitude.toFixed(4)}, ${longitude.toFixed(4)}`;
      setDisplayName(name);
      setGeoStatus(null);
      void handleSave(latitude, longitude, name);
      setGeoStatus("✓ " + t("settings.location.saved"));
    }, () => {
      setGeoStatus(t("settings.location.blocked"));
    });
  }, [t]);

  const handleGeocode = async () => {
    if (!cityInput.trim()) return;
    setSaving(true);
    setGeoStatus(t("settings.location.looking_up"));
    const result = await geocodeCity(
      cityInput.trim(),
      countryInput.trim(),
    );
    setSaving(false);
    if (!result) {
      setGeoStatus(t("settings.location.not_found"));
      return;
    }
    setDisplayName(result.display_name);
    setGeoStatus(null);
    void handleSave(result.lat, result.lon, result.display_name);
    setGeoStatus("✓ " + t("settings.location.saved"));
  };

  if (loading) return <div className={styles.status}>Loading…</div>;

  return (
    <div className={styles.wrap}>
      <p className={styles.desc}>{t("settings.location.description")}</p>

      {displayName ? (
        <div className={styles.status}>
          {t("settings.location.current")}: {displayName}
        </div>
      ) : (
        <div className={styles.status}>
          {t("settings.location.no_location")}
        </div>
      )}

      <div className={styles.row}>
        <div className="d-inline-flex align-items-center gap-2">
          <span className={styles.label}>
            {autoUpdate
              ? t("settings.location.auto_update_on")
              : t("settings.location.use_current")}
          </span>
          <Toggle
            checked={autoUpdate}
            onChange={handleToggleAuto}
            ariaLabel={t("settings.location.use_current")}
          />
        </div>

        {!autoUpdate && (
          <SettingsButton
            variant="secondary"
            className="d-inline-flex align-items-center gap-2"
            onClick={handleOneShotBrowser}
            disabled={saving}
          >
            <MapPin size={14} />
            {t("settings.location.detect_once")}
          </SettingsButton>
        )}
      </div>

      {geoStatus && <div className={styles.status}>{geoStatus}</div>}

      <div className={styles.sepRow}>
        <div className={styles.sepLine} />
        {t("settings.location.or_manually")}
        <div className={styles.sepLine} />
      </div>

      <div className={styles.row}>
        <input
          placeholder={t("settings.location.city")}
          value={cityInput}
          onChange={(e) => setCityInput(e.target.value)}
          className={styles.input}
        />
        <input
          placeholder={t("settings.location.country")}
          value={countryInput}
          onChange={(e) => setCountryInput(e.target.value)}
          className={styles.input}
        />
      </div>

      <SettingsButton
        variant="primary"
        onClick={handleGeocode}
        disabled={saving || !cityInput.trim()}
      >
        {t("settings.location.search")}
      </SettingsButton>
    </div>
  );
}
