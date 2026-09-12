import { useState, useEffect } from "react";
import Modal from "react-bootstrap/Modal";
import Form from "react-bootstrap/Form";
import Button from "react-bootstrap/Button";
import { Unlock, Lock } from "lucide-react";
import styles from "./CanvasSettingsModal.module.css";

interface CanvasSettingsModalProps {
  show: boolean;
  documentWidth: number;
  documentHeight: number;
  documentBgColor: string;
  onApply: (width: number, height: number, bgColor: string) => void;
  onHide: () => void;
  /** When true, shows "New Document" title and resets on apply. */
  newDocumentMode?: boolean;
}

const PRESET_COLORS = [
  { label: "Transparent", value: "transparent" },
  { label: "White",       value: "#ffffff" },
  { label: "Black",       value: "#000000" },
];

export default function CanvasSettingsModal({
  show,
  documentWidth,
  documentHeight,
  documentBgColor,
  onApply,
  onHide,
  newDocumentMode,
}: CanvasSettingsModalProps) {
  const [w, setW] = useState(documentWidth);
  const [h, setH] = useState(documentHeight);
  const [bg, setBg] = useState(documentBgColor);
  const [aspectLocked, setAspectLocked] = useState(false);
  const [customColor, setCustomColor] = useState(
    PRESET_COLORS.some((p) => p.value === documentBgColor) ? "#808080" : documentBgColor,
  );

  useEffect(() => {
    if (show) {
      setW(documentWidth);
      setH(documentHeight);
      setBg(documentBgColor);
      setAspectLocked(false);
    }
  }, [show, documentWidth, documentHeight, documentBgColor]);

  const aspect = documentWidth / documentHeight;

  const handleWChange = (val: number) => {
    setW(val);
    if (aspectLocked && val > 0) setH(Math.round(val / aspect));
  };

  const handleHChange = (val: number) => {
    setH(val);
    if (aspectLocked && val > 0) setW(Math.round(val * aspect));
  };

  const handleWBlur = () => {
    const clamped = Math.max(8, w);
    setW(clamped);
    if (aspectLocked) setH(Math.max(8, Math.round(clamped / aspect)));
  };

  const handleHBlur = () => {
    const clamped = Math.max(8, h);
    setH(clamped);
    if (aspectLocked) setW(Math.max(8, Math.round(clamped * aspect)));
  };

  const isCustom = !PRESET_COLORS.some((p) => p.value === bg);

  return (
    <Modal
      show={show}
      onHide={onHide}
      centered
      size="sm"
      contentClassName="bg-dark"
    >
      <Modal.Header
        closeButton
        closeVariant="white"
        className={styles.modalHeader}
      >
        <Modal.Title className={styles.modalTitle}>
          {newDocumentMode ? "New Document" : "Canvas Settings"}
        </Modal.Title>
      </Modal.Header>
      <Modal.Body className={styles.modalBody}>
        <Form.Group className="mb-3">
          <Form.Label className="text-theme-secondary">
            Canvas Size
          </Form.Label>
          <div className="d-flex gap-2 align-items-center">
            <div className="d-flex align-items-center gap-1">
              <span className={styles.dimLabel}>W</span>
              <Form.Control
                type="number"
                value={w}
                onChange={(e) => handleWChange(Number(e.target.value))}
                onBlur={handleWBlur}
                size="sm"
                className={styles.formControl}
              />
            </div>
            <button
              title={aspectLocked ? "Unlock aspect ratio" : "Lock aspect ratio"}
              onClick={() => setAspectLocked(!aspectLocked)}
              className={styles.lockBtn}
              // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
              style={{
                color: aspectLocked ? "#6399ff" : "rgba(var(--theme-text-rgb), 0.4)",
              }}
            >
              {aspectLocked ? <Lock size={14} /> : <Unlock size={14} />}
            </button>
            <div className="d-flex align-items-center gap-1">
              <span className={styles.dimLabel}>H</span>
              <Form.Control
                type="number"
                value={h}
                onChange={(e) => handleHChange(Number(e.target.value))}
                onBlur={handleHBlur}
                size="sm"
                className={styles.formControl}
              />
            </div>
          </div>
        </Form.Group>

        <Form.Group className="mb-1">
          <Form.Label className="text-theme-secondary">
            Background
          </Form.Label>
          <div className="d-flex flex-wrap gap-2">
            {PRESET_COLORS.map((p) => (
              <button
                key={p.value}
                onClick={() => setBg(p.value)}
                title={p.label}
                className={styles.presetBtn}
                // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
                style={{
                  border: bg === p.value
                    ? "1.5px solid #6399ff"
                    : "1px solid var(--theme-border)",
                  background: p.value === "transparent"
                    ? "repeating-linear-gradient(45deg,#555 0,#555 4px,#888 4px,#888 8px)"
                    : p.value,
                  color: p.value === "#000000" ? "#fff"
                    : p.value === "transparent" ? "#fff"
                    : "var(--theme-text)",
                }}
              >
                {p.label}
              </button>
            ))}
            <label className={styles.customLabel}>
              <div
                className={styles.customSwatch}
                // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
                style={{
                  background: customColor,
                  border: isCustom
                    ? "1.5px solid #6399ff"
                    : "1px solid var(--theme-border)",
                }}
              />
              <span className="text-section-label">
                Custom
              </span>
              <input
                type="color"
                value={customColor}
                onChange={(e) => { setCustomColor(e.target.value); setBg(e.target.value); }}
                className={styles.customColorInput}
              />
            </label>
          </div>
        </Form.Group>
      </Modal.Body>
      <Modal.Footer className={styles.modalFooter}>
        <Button variant="outline-secondary" size="sm" onClick={onHide}>Cancel</Button>
        <Button variant="primary" size="sm" onClick={() => { onApply(w, h, bg); onHide(); }}>
          {newDocumentMode ? "Create" : "Apply"}
        </Button>
      </Modal.Footer>
    </Modal>
  );
}
