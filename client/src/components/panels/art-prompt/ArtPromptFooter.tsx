import ProgressBar from "react-bootstrap/ProgressBar";
import LucideIcon from "../../shared/LucideIcon";
import styles from "./ArtPromptFooter.module.css";

export default function ArtPromptFooter({
  progress,
  generating,
  hasPrompt,
  onSubmit,
  onCancel,
}: {
  progress: number;
  generating: boolean;
  hasPrompt: boolean;
  onSubmit: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="flex-shrink-0 mt-2">
      <div className="d-flex align-items-center gap-2">
        <div className="flex-grow-1">
          <ProgressBar
            now={generating ? Math.max(progress, 2) : progress}
            variant={generating ? "info" : "secondary"}
            className={styles.progressBar}
            animated={generating}
            striped={generating}
          />
        </div>
        {generating ? (
          <button
            className={`btn btn-sm btn-danger p-1 ${styles.cancelBtn}`}
            onClick={onCancel}
            title="Cancel image generation"
          >
            <LucideIcon name="circle-stop" size={16} />
          </button>
        ) : (
          <button
            className={`btn btn-sm p-1 d-flex align-items-center justify-content-center ${styles.submitBtn}`}
            onClick={onSubmit}
            disabled={!hasPrompt}
            title="Generate image"
          >
            <LucideIcon name="chevron-up" size={16} />
          </button>
        )}
      </div>
    </div>
  );
}
