import { useState, useEffect } from "react";
import Modal from "react-bootstrap/Modal";
import Form from "react-bootstrap/Form";
import Button from "react-bootstrap/Button";
import styles from "./NewLayerModal.module.css";

const PRESET_COLORS = [
  { label: "Transparent", value: "transparent" },
  { label: "White",       value: "#ffffff" },
  { label: "Black",       value: "#000000" },
];

interface NewLayerModalProps {
  show: boolean;
  onConfirm: (name: string, opacity: number, fillColor: string) => void;
  onHide: () => void;
  layerIndex: number;
  defaultName: string;
}

export default function NewLayerModal({
  show,
  onConfirm,
  onHide,
  defaultName,
}: NewLayerModalProps) {
  const [name, setName] = useState(defaultName);

  useEffect(() => {
    if (show) setName(defaultName);
  }, [show, defaultName]);
  const [opacity, setOpacity] = useState(1);
  const [fillColor, setFillColor] = useState("transparent");

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
          New Layer
        </Modal.Title>
      </Modal.Header>
      <Modal.Body className={styles.modalBody}>
        <Form.Group className="mb-2">
          <Form.Label className={`text-theme-secondary ${styles.formLabel}`}>
            Name
          </Form.Label>
          <Form.Control
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            size="sm"
            className={styles.formControl}
          />
        </Form.Group>
        <Form.Group className="mb-2">
          <Form.Label className={`text-theme-secondary ${styles.formLabel}`}>
            Opacity
          </Form.Label>
          <div className="d-flex align-items-center gap-2">
            <Form.Range
              min={0} max={1} step={0.01}
              value={opacity}
              onChange={(e) => setOpacity(Number(e.target.value))}
              className="flex-grow-1"
            />
            <span className={styles.percentText}>
              {Math.round(opacity * 100)}%
            </span>
          </div>
        </Form.Group>
        <Form.Group className="mb-1">
          <Form.Label className={`text-theme-secondary ${styles.formLabel}`}>
            Fill Color
          </Form.Label>
          <div className="d-flex flex-wrap gap-2">
            {PRESET_COLORS.map((p) => {
              const isSelected = fillColor === p.value;
              return (
                <button
                  key={p.value}
                  onClick={() => setFillColor(p.value)}
                  title={p.label}
                  className={styles.presetBtn}
                  // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
                  style={{
                    border: isSelected
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
              );
            })}
            <label className={styles.customLabel}>
              <div
                className={styles.customSwatch}
                // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
                style={{
                  background: fillColor === "transparent" ? "#808080" : fillColor,
                  border: !PRESET_COLORS.some((p) => p.value === fillColor)
                    ? "1.5px solid #6399ff"
                    : "1px solid var(--theme-border)",
                }}
              />
              <span className="text-section-label">
                Custom
              </span>
              <input
                type="color"
                value={fillColor === "transparent" ? "#808080" : fillColor}
                onChange={(e) => setFillColor(e.target.value)}
                className={styles.customColorInput}
              />
            </label>
          </div>
        </Form.Group>
      </Modal.Body>
      <Modal.Footer className={styles.modalFooter}>
        <Button variant="outline-secondary" size="sm" onClick={onHide}>Cancel</Button>
        <Button variant="primary" size="sm" onClick={() => { onConfirm(name, opacity, fillColor); onHide(); }}>
          Add Layer
        </Button>
      </Modal.Footer>
    </Modal>
  );
}
