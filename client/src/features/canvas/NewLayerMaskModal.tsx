import { useState } from "react";
import Modal from "react-bootstrap/Modal";
import Button from "react-bootstrap/Button";
import styles from "./NewLayerMaskModal.module.css";

type MaskFill = "white" | "black";

interface Props {
  show: boolean;
  layerName: string;
  onAdd: (fill: MaskFill, invert: boolean) => void;
  onHide: () => void;
}

const INIT_OPTIONS: { value: MaskFill | "alpha" | "transfer-alpha" | "grayscale"; label: string }[] = [
  { value: "white",         label: "White (full opacity)" },
  { value: "black",         label: "Black (full transparency)" },
  { value: "alpha",         label: "Layer's alpha channel" },
  { value: "transfer-alpha",label: "Transfer layer's alpha channel" },
  { value: "grayscale",     label: "Grayscale copy of layer" },
];

export default function NewLayerMaskModal({ show, layerName, onAdd, onHide }: Props) {
  const [init, setInit] = useState<string>("white");
  const [invert, setInvert] = useState(false);

  const handleAdd = () => {
    const fill: MaskFill = init === "black" ? "black" : "white";
    onAdd(fill, invert);
    setInit("white");
    setInvert(false);
  };

  return (
    <Modal show={show} onHide={onHide} size="sm" centered dialogClassName="layer-mask-modal">
      <Modal.Header closeButton className={styles.header}>
        <Modal.Title className={styles.title}>
          Add Layer Mask
        </Modal.Title>
      </Modal.Header>
      <Modal.Body className={styles.body}>
        <div className={styles.section}>
          <span className="layer-mask-field-label">Layer: {layerName}</span>
        </div>
        <div className={styles.section}>
          <span className="layer-mask-field-label">Initialize Layer Mask to:</span>
          {INIT_OPTIONS.map((opt) => (
            <label key={opt.value} className="layer-mask-radio-label">
              <input
                type="radio"
                name="maskInit"
                value={opt.value}
                checked={init === opt.value}
                onChange={() => setInit(opt.value)}
                className={styles.radioInput}
              />
              {opt.label}
            </label>
          ))}
        </div>
        <label className={`layer-mask-radio-label ${styles.separator}`}>
          <input
            type="checkbox"
            checked={invert}
            onChange={(e) => setInvert(e.target.checked)}
            className={styles.checkboxInput}
          />
          Invert mask
        </label>
      </Modal.Body>
      <Modal.Footer className={styles.footer}>
        <Button variant="outline-secondary" size="sm" onClick={onHide} className={styles.footerBtn}>
          Cancel
        </Button>
        <Button variant="primary" size="sm" onClick={handleAdd} className={styles.footerBtn}>
          Add
        </Button>
      </Modal.Footer>
    </Modal>
  );
}
