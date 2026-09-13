import { useRef, useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import styles from "./ImageUpload.module.css";

export type ImageType = "avatar" | "banner";

interface ImageUploadProps {
  imageType: ImageType;
  onUploaded: (b64: string) => void;
  children: React.ReactNode;
  accept?: string;
  maxBytes?: number;
  style?: React.CSSProperties;
}

export default function ImageUpload({
  imageType,
  onUploaded,
  children,
  accept = "image/*",
  maxBytes = 2 * 1024 * 1024,
  style,
}: ImageUploadProps) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleClick = useCallback(() => {
    inputRef.current?.click();
  }, []);

  const handleFile = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      setError(null);
      if (file.size > maxBytes) {
        setError(t("user.image_upload.too_large", { max: maxBytes / (1024 * 1024) }));
        return;
      }
      setUploading(true);
      try {
        const b64 = await fileToBase64(file);
        const { uploadProfileImage } = await import(
          "../../api/user"
        );
        const result = await uploadProfileImage(imageType, b64);
        if (result) {
          onUploaded(result);
        } else {
          setError(t("user.image_upload.upload_failed"));
        }
      } catch {
        setError(t("user.image_upload.upload_failed"));
      } finally {
        setUploading(false);
        if (inputRef.current) inputRef.current.value = "";
      }
    },
    [imageType, maxBytes, onUploaded],
  );

  return (
    <div
      onClick={handleClick}
      className={styles.clickable}
      style={style}
      title={t("user.image_upload.click_to_change", { type: imageType })}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        className={styles.hiddenInput}
        onChange={handleFile}
      />
      {children}
      {uploading && (
        <div className={styles.uploadOverlay}>
          {t("user.image_upload.uploading")}
        </div>
      )}
      {error && (
        <div className={styles.errorToast}>
          {error}
        </div>
      )}
    </div>
  );
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result;
      if (typeof result === "string") {
        resolve(result);
      } else {
        reject(new Error("Failed to read file"));
      }
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}
