import { useState } from "react";
import { useTranslation } from "react-i18next";
import { MapPin } from "lucide-react";
import { LocationManualForm } from "./LocationManualForm";
import { WizardButton } from "./WizardButton";
import styles from "./LocationStep.module.css";

interface Props { onSave: (lat: number, lon: number, displayName: string) => void; onSkip: () => void; }

export function LocationStep({ onSave, onSkip }: Props) {
  const { t } = useTranslation();
  const [geoStatus, setGeoStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const handleBrowserGeo = () => {
    if (!navigator.geolocation) { setGeoStatus(t("setup.location.not_available")); return; }
    setBusy(true); setGeoStatus(t("setup.location.detecting"));
    navigator.geolocation.getCurrentPosition(
      (pos) => { setBusy(false); setGeoStatus(null); onSave(pos.coords.latitude, pos.coords.longitude, "Your location"); },
      () => { setBusy(false); setGeoStatus(t("setup.location.blocked")); },
    );
  };

  return (
    <div className={styles.wrap}>
      <p className={`m-0 ${styles.desc}`}>{t("setup.location.desc")}</p>
      <WizardButton variant="secondary" className={`d-inline-flex align-items-center justify-content-center gap-2 w-100 ${styles.geoBtn}`}
        onClick={handleBrowserGeo} disabled={busy}>
        <MapPin size={16} />{t("setup.location.use_current")}
      </WizardButton>
      {geoStatus && <div className={`small text-center ${styles.statusText}`}>{geoStatus}</div>}
      <div className={`d-flex align-items-center gap-2 ${styles.sepRow}`}>
        <div className={styles.sepLine} />{t("setup.location.or_manually")}<div className={styles.sepLine} />
      </div>
      <LocationManualForm onSave={onSave} onSkip={onSkip} />
    </div>
  );
}
