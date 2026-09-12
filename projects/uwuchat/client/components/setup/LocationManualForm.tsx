import { useState } from "react";
import { useTranslation } from "react-i18next";
import { geocodeCity } from "../../api/user";
import { WizardButton } from "./WizardButton";
import styles from "./LocationManualForm.module.css";

interface Props { onSave: (lat: number, lon: number, displayName: string) => void; onSkip: () => void; }

export function LocationManualForm({ onSave, onSkip }: Props) {
  const { t } = useTranslation();
  const [city, setCity] = useState(""); const [country, setCountry] = useState("");
  const [status, setStatus] = useState<string | null>(null); const [busy, setBusy] = useState(false);

  const handleSubmit = async () => {
    if (!city.trim()) { setStatus(t("setup.location.city_required")); return; }
    setBusy(true); setStatus(t("setup.location.looking_up"));
    const result = await geocodeCity(city.trim(), country.trim());
    setBusy(false);
    if (!result) { setStatus(t("setup.location.not_found")); return; }
    onSave(result.lat, result.lon, result.display_name);
  };

  return (
    <div className={styles.wrap}>
      <input placeholder={t("setup.location.city_placeholder")} value={city} onChange={(e) => setCity(e.target.value)} className={styles.input} />
      <input placeholder={t("setup.location.country_placeholder")} value={country} onChange={(e) => setCountry(e.target.value)} className={styles.input} />
      {status && <div className={`small ${styles.status}`}>{status}</div>}
      <div className="d-flex gap-2">
        {/* eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation */}
        <WizardButton variant="primary" className="flex-fill" style={{ opacity: busy ? 0.6 : 1 }} onClick={handleSubmit} disabled={busy}>{t("setup.location.save_location")}</WizardButton>
        <WizardButton variant="secondary" onClick={onSkip}>{t("setup.location.skip")}</WizardButton>
      </div>
    </div>
  );
}
