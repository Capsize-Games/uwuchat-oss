import { useEffect, useCallback, useState } from "react";
import CivitaiImage from "./CivitaiImage";
import { startCivitaiFileDownload, cancelDownloadJob } from "../../../api/downloads";
import { useDownloads } from "../../edge/downloads/useDownloadState";
import { DownloadButton, ApiKeyPrompt } from "./CivitaiModelDetailDownload";
import type { ModelDetailData, VersionImage } from "./CivitaiModelDetailTypes";
import { useCivitaiPrefs } from "../../../hooks/useCivitaiPrefs";
import styles from "./CivitaiModelDetailModal.module.css";

interface CivitaiModelDetailModalProps {
  model: ModelDetailData | null;
  onClose: () => void;
  loading?: boolean;
  baseModel?: string;
  modelType?: string;
  onVersionChange?: (versionId: number) => void;
}

const MODAL_W = 740;
const MODAL_H = 520;
const _VIDEO_EXTS = [".mp4", ".webm", ".mov", ".avi"];

function _isVideoUrl(url: string): boolean {
  const clean = url.split("?")[0].toLowerCase();
  return _VIDEO_EXTS.some((ext) => clean.endsWith(ext));
}

function _firstImageUrl(images: { url?: string }[]): string {
  for (const img of images) {
    if (img.url && !_isVideoUrl(img.url)) return img.url;
  }
  return "";
}

function stripHtml(html: string): string {
  if (typeof DOMParser !== "undefined") {
    const doc = new DOMParser().parseFromString(html, "text/html");
    return (doc.body.textContent ?? "").trim();
  }
  return html.replace(/<[^>]*>/g, "").trim();
}

export default function CivitaiModelDetailModal({
  model,
  onClose,
  loading: _loading,
  baseModel: currentBaseModel,
  modelType: currentModelType,
  onVersionChange,
}: CivitaiModelDetailModalProps) {
  const [selectedVersionId, setSelectedVersionId] = useState<number | null>(null);
  const [selectedFileId, setSelectedFileId] = useState<number | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string>("");
  const [previewBase64, setPreviewBase64] = useState<string>("");
  const { downloads, addDownload, removeDownload, isDownloaded: _isDownloaded } = useDownloads();
  const [showApiKeyPrompt, setShowApiKeyPrompt] = useState(false);
  const { apiKey } = useCivitaiPrefs();
  const [_pendingFileName, setPendingFileName] = useState<string>("");

  const versions = model?.versions ?? [];

  useEffect(() => {
    const v0 = model?.versions?.[0];
    if (!v0) return;
    setSelectedVersionId(v0.id);
    const files = v0.files ?? [];
    setSelectedFileId(files.length > 0 ? files[0].id : null);
    const images = v0.images ?? [];
    const firstUrl = _firstImageUrl(images);
    const firstImg = images.find((img) => img.url === firstUrl);
    setPreviewImage(firstImg);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [model?.id, model?.versions?.length]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    },
    [onClose],
  );

  useEffect(() => {
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  if (!model) return null;

  const selectedVersion = versions.find((v) => v.id === selectedVersionId) ?? null;
  const selectedFile = (selectedVersion?.files ?? []).find(
    (f) => f.id === selectedFileId,
  ) ?? null;

  const stats = model.stats ?? {};
  const desc = model.description ? stripHtml(model.description) : "";

  const setPreviewImage = (img: VersionImage | undefined) => {
    if (!img) return;
    setPreviewUrl(img.url);
    const full = img.images_base64?.full || "";
    const small = img.images_base64?.small || "";
    setPreviewBase64(full || small);
  };

  // Derive live base64 for the current preview URL from up-to-date model data,
  // so the large preview updates automatically when streaming thumbnails arrive.
  const livePreviewImg = (selectedVersion?.images ?? []).find((img) => img.url === previewUrl);
  const livePreviewBase64 = livePreviewImg?.images_base64?.full
    || livePreviewImg?.images_base64?.small
    || previewBase64;

  const handleVersionChange = (vid: number) => {
    setSelectedVersionId(vid);
    const v = versions.find((ver) => ver.id === vid);
    const files = v?.files ?? [];
    setSelectedFileId(files.length > 0 ? files[0].id : null);
    const images = v?.images ?? [];
    const firstUrl = _firstImageUrl(images);
    const firstImg = images.find((img) => img.url === firstUrl);
    setPreviewImage(firstImg);
    const needsThumbnails = images.some((img) => !img.images_base64?.small);
    if (needsThumbnails) onVersionChange?.(vid);
  };

  const handleThumbnailClick = (img: VersionImage) => {
    setPreviewImage(img);
  };

  const handleDownload = async (key?: string) => {
    if (!selectedFile?.downloadUrl) return;
    try {
      const result = await startCivitaiFileDownload({
        url: selectedFile.downloadUrl,
        output_path: `/tmp/airunner/downloads/${selectedFile.name}`,
        api_key: key ?? "",
        base_model: currentBaseModel,
        model_type: currentModelType,
      });
      if (result.job_id) {
        addDownload({
          jobId: result.job_id,
          label: selectedFile.name,
          modelName: model?.name,
          baseModel: currentBaseModel,
          modelType: currentModelType,
          startedAt: new Date().toISOString(),
          downloadUrl: selectedFile.downloadUrl,
        });
      }
    } catch { /* */ }
  };

  const handleDownloadClick = () => {
    if (!selectedFile?.downloadUrl) return;
    setPendingFileName(selectedFile.name ?? "");
    if (apiKey) {
      handleDownload(apiKey);
    } else {
      setShowApiKeyPrompt(true);
    }
  };

  const handleApiKeySubmit = (key: string) => {
    setShowApiKeyPrompt(false);
    handleDownload(key);
  };

  return (
    <div
      className="image-preview-backdrop"
      onClick={onClose}
    >
      <div
        className={styles.modalContent}
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          className={styles.closeBtn}
          title="Close (Esc)"
        >
          ✕
        </button>

        {/* ── Left column: preview + thumbnails ── */}
        <div className={`d-flex flex-column flex-shrink-0 ${styles.previewColumn}`}>
          <div
            className={`flex-grow-1 d-flex align-items-center justify-content-center min-h-0 ${styles.previewFrame}`}
          >
            {previewUrl || livePreviewBase64 ? (
              <CivitaiImage
                url={previewUrl}
                alt=""
                base64={livePreviewBase64}
                width={400}
                className={styles.previewImage}
              />
            ) : (
              <div className={styles.noPreview}>No preview</div>
            )}
          </div>

          {/* Thumbnails below preview */}
          {(selectedVersion?.images ?? []).length > 0 && (
            <div className={`flex-shrink-0 d-flex flex-wrap ${styles.thumbnails}`}>
              {(selectedVersion?.images ?? [])
                .filter((img) => img.nsfw !== "X")
                .slice(0, 8)
                .map((img) => (
                  <div
                    key={img.url}
                    onClick={() => handleThumbnailClick(img)}
                    className={`${styles.thumbItem} ${
                      previewUrl === img.url ? styles.thumbItemActive : styles.thumbItemInactive
                    }`}
                  >
                    <CivitaiImage
                      url={img.url} alt=""
                      base64={img.images_base64?.small}
                      width={40}
                      className={styles.thumbImage}
                    />
                  </div>
                ))}
            </div>
          )}
        </div>

        {/* ── Right column: info + selects + buttons ── */}
        <div className={`flex-grow-1 d-flex flex-column overflow-hidden ${styles.infoColumn}`}>
          {/* Header */}
          <div className="flex-shrink-0">
            <div className={styles.modelName}>
              {model.name}
            </div>
            <div className={styles.modelCreator}>
              {model.creator ?? "Unknown"}
              {model.type ? ` · ${model.type}` : ""}
            </div>
            <div className={`d-flex ${styles.modelStats}`}>
              <span>⬇ {stats.downloadCount ?? 0}</span>
              <span>★ {stats.favoriteCount ?? 0}</span>
              <span>💬 {stats.commentCount ?? 0}</span>
            </div>
          </div>

          {/* License badges */}
          {model && (
            <div className={`d-flex flex-wrap flex-shrink-0 ${styles.licenseIcons}`}>
              {model.allowNoCredit === true && <span className={styles.licenseIcon} title="Use without credit">🙏</span>}
              {model.allowCommercialUse === "Commercial" && <span className={styles.licenseIcon} title="Commercial use allowed">💰</span>}
              {model.allowCommercialUse === "Non-Commercial" && <span className={styles.licenseIcon} title="Non-commercial only">🚫💰</span>}
              {model.allowDerivatives === "Allowed" && <span className={styles.licenseIcon} title="Derivatives allowed">🔀</span>}
              {model.allowDerivatives === "Not allowed" && <span className={styles.licenseIcon} title="No derivatives">🚫🔀</span>}
              {model.allowDifferentLicense === true && <span className={styles.licenseIcon} title="Can use different license">📜</span>}
            </div>
          )}

          {/* Scrollable description */}
          <div
            className={`civitai-model-description scrollable-modal-content scroll-panel ${styles.descriptionArea}`}
          >
            {desc || "No description available."}
          </div>

          {/* Version / File selects (anchored to bottom) */}
          <div className="flex-shrink-0">
            {versions.length > 0 && (
              <div className={styles.controlsSection}>
                <div className={styles.controlLabel}>Version</div>
                <select
                  value={selectedVersionId ?? ""}
                  onChange={(e) => handleVersionChange(Number(e.target.value))}
                  className={styles.selectInput}
                >
                  {versions.map((v) => (
                    <option key={v.id} value={v.id} className={styles.selectOption}>
                      {v.name}
                    </option>
                  ))}
                </select>
              </div>
            )}
            {(selectedVersion?.files ?? []).length > 0 && (
              <div className={styles.controlsSection}>
                <div className={styles.controlLabel}>File</div>
                <select
                  value={selectedFileId ?? ""}
                  onChange={(e) => setSelectedFileId(Number(e.target.value))}
                  className={styles.selectInput}
                >
                  {(selectedVersion?.files ?? []).map((f) => (
                    <option key={f.id} value={f.id} className={styles.selectOption}>
                      {f.name}
                      {f.sizeKB ? ` (${(f.sizeKB / 1024 / 1024).toFixed(1)} GB)` : ""}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>

          {/* Action buttons */}
          <div className={`d-flex flex-shrink-0 ${styles.actionRow}`}>
            <DownloadButton
              selectedFile={selectedFile}
              downloads={downloads}
              onDownloadClick={handleDownloadClick}
              onCancel={async (jobId: string) => {
                try { await cancelDownloadJob(jobId); } catch { /* */ }
                removeDownload(jobId);
              }}
            />
            <button
              onClick={() => window.open(`https://civitai.com/models/${model.id}`, "_blank")}
              className={styles.viewOnCivitBtn}
            >
              ↗ CivitAI
            </button>
          </div>
        </div>
      </div>

      {showApiKeyPrompt && (
        <ApiKeyPrompt
          onSubmit={handleApiKeySubmit}
          onCancel={() => setShowApiKeyPrompt(false)}
        />
      )}
    </div>
  );
}
