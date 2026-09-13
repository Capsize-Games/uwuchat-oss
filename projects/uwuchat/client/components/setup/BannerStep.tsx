import { useState, useRef } from "react";
import { useTranslation } from "react-i18next";
import { uploadProfileImage } from "../../api/user";
import { WizardButton } from "./WizardButton";
import styles from "./StepShared.module.css";

interface Props { onSkip: () => void; }

export function BannerStep({ onSkip }: Props) {
  const { t } = useTranslation();
  const [preview, setPreview] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [saved, setSaved] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]; if (!file) return;
    setUploading(true);
    const reader = new FileReader();
    reader.onload = () => {
      const base64 = reader.result as string; setPreview(base64);
      uploadProfileImage("banner", base64).then((result) => { setUploading(false); if (result) setSaved(true); }).catch(() => setUploading(false));
    };
    reader.readAsDataURL(file);
  };

  return (
    <div className={styles.wrap}>
      <p className={`small ${styles.desc}`}>{t("setup.steps.banner_desc")}</p>
      <div onClick={() => fileRef.current?.click()} className={`${styles.bannerUpload} ${preview ? styles.uploadPreview : ""}`}
        style={preview ? { "--preview-url": `url(${preview}) center/cover` } as React.CSSProperties : undefined}>
        {!preview && <span className={styles.uploadIcon}>🖼️</span>}
      </div>
      <input ref={fileRef} type="file" accept="image/*" className={styles.hiddenInput} onChange={handleFile} />
      <div className={styles.btnRowCenter}>
        <WizardButton variant="primary" size="lg" onClick={() => fileRef.current?.click()} disabled={uploading}>
          {uploading ? t("setup.steps.uploading") : saved ? "✓ " + t("setup.steps.upload_banner") : t("setup.steps.upload_banner")}</WizardButton>
        <WizardButton variant={saved ? "primary" : "secondary"} size="lg" onClick={onSkip}>
          {saved ? t("setup.steps.done") : t("setup.steps.skip")}</WizardButton>
      </div>
    </div>
  );
}
