import { useState } from "react";
import CivitaiImage from "./CivitaiImage";
import styles from "./CivitaiSampleImages.module.css";

interface CivitaiImageInfo {
  url: string;
  nsfw?: string;
  width?: number;
  height?: number;
}

interface CivitaiSampleImagesProps {
  images: CivitaiImageInfo[];
}

export default function CivitaiSampleImages({
  images,
}: CivitaiSampleImagesProps) {
  const [selectedUrl, setSelectedUrl] = useState<string | null>(
    images.length > 0 ? images[0].url : null,
  );

  if (!images || images.length === 0) return null;

  const preview = images.find((img) => img.url === selectedUrl);

  return (
    <div className="mb-2">
      <small className="text-muted d-block mb-1">Sample Images</small>

      {/* Preview */}
      {preview && (
        <div className={styles.preview}>
          <CivitaiImage
            url={preview.url}
            alt="Preview"
            width={400}
            className={styles.previewImage}
          />
        </div>
      )}

      {/* Thumbnail strip */}
      <div className={styles.thumbStrip}>
        {images.slice(0, 10).map((img) => (
          <div
            key={img.url}
            onClick={() => setSelectedUrl(img.url)}
            className={
              selectedUrl === img.url
                ? styles.thumbItemSelected
                : styles.thumbItem
            }
          >
            <CivitaiImage
              url={img.url}
              alt="Thumb"
              width={48}
              className={styles.thumbImage}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
