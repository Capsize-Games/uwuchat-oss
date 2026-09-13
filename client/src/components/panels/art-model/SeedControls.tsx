import Form from "react-bootstrap/Form";
import LucideIcon from "../../shared/LucideIcon";
import styles from "./SeedControls.module.css";

export default function SeedControls({
  seed,
  seedRandomized,
  loading,
  onSeedChange,
  onToggleRandom,
}: {
  seed: number;
  seedRandomized: boolean;
  loading: boolean;
  onSeedChange: (v: number) => void;
  onToggleRandom: () => void;
}) {
  return (
    <Form.Group className="mb-2">
      <div className="d-flex align-items-center">
        <span className={seedRandomized ? styles.labelDimmed : styles.label}>
          Seed
        </span>
        <Form.Control
          size="sm"
          value={seed}
          readOnly={seedRandomized}
          disabled={loading}
          className={seedRandomized ? styles.inputDimmed : styles.input}
          onChange={(e) => {
            const raw = e.target.value.replace(/[^0-9-]/g, "");
            if (raw === "") return;
            const v = Number(raw);
            if (isNaN(v)) return;
            onSeedChange(v);
          }}
        />
        <button
          type="button"
          className={`btn btn-sm p-1 ${seedRandomized ? styles.toggleBtnActive : styles.toggleBtnDimmed}`}
          onClick={onToggleRandom}
          title={
            seedRandomized
              ? "Use a fixed seed"
              : "Randomize seed on each generation"
          }
        >
          <LucideIcon
            name="dices"
            size={16}
            className={seedRandomized ? "icon-white" : "icon-muted"}
          />
        </button>
      </div>
    </Form.Group>
  );
}
