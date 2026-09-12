import Modal from "react-bootstrap/Modal";
import Button from "react-bootstrap/Button";
import styles from "./ImageDropModal.module.css";

export type DropResizeMode = "none" | "fit-canvas";

interface ImageDropModalProps {
  show: boolean;
  naturalW: number;
  naturalH: number;
  gridW: number;
  gridH: number;
  canvasW: number;
  canvasH: number;
  onConfirm: (mode: DropResizeMode) => void;
  onHide: () => void;
}

function fitDimensions(
  srcW: number,
  srcH: number,
  maxW: number,
  maxH: number,
): { w: number; h: number } {
  const ratio = Math.min(maxW / srcW, maxH / srcH, 1);
  return { w: Math.round(srcW * ratio), h: Math.round(srcH * ratio) };
}

export default function ImageDropModal({
  show,
  naturalW,
  naturalH,
  gridW,
  gridH,
  canvasW,
  canvasH,
  onConfirm,
  onHide,
}: ImageDropModalProps) {
  const fitCanvas = fitDimensions(naturalW, naturalH, canvasW, canvasH);

  const options: { mode: DropResizeMode; label: string; detail: string }[] = [
    { mode: "none",       label: "Original size",        detail: `${naturalW} × ${naturalH}` },
    { mode: "fit-canvas", label: "Fit to Canvas",        detail: `→ ${fitCanvas.w} × ${fitCanvas.h}` },
  ];

  return (
    <Modal show={show} onHide={onHide} centered size="sm" contentClassName="bg-dark text-light border-secondary">
      <Modal.Header closeButton closeVariant="white" className={styles.modalHeader}>
        <Modal.Title className={styles.modalTitle}>Place Image</Modal.Title>
      </Modal.Header>
      <Modal.Body className="d-flex flex-column gap-2">
        {options.map(({ mode, label, detail }) => (
          <button
            key={mode}
            onClick={() => { onConfirm(mode); onHide(); }}
            className={styles.optionBtn}
          >
            <span>{label}</span>
            <span className={styles.optionDetail}>{detail}</span>
          </button>
        ))}
      </Modal.Body>
      <Modal.Footer className={styles.modalFooter}>
        <Button variant="outline-secondary" size="sm" onClick={onHide}>Cancel</Button>
      </Modal.Footer>
    </Modal>
  );
}

export { fitDimensions };
