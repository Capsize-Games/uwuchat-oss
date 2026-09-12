import Form from "react-bootstrap/Form";
import styles from "./OpacitySlider.module.css";

interface OpacitySliderProps {
  value: number;
  onChange: (val: number) => void;
}

export default function OpacitySlider({ value, onChange }: OpacitySliderProps) {
  return (
    <div className={`flex-shrink-0 border-b-subtle ${styles.root}`}>
      <div className={styles.wrapper}>
        <span className={styles.label}>
          Opacity
        </span>
        <div className={styles.sliderWrap}>
          <Form.Range
            min={0} max={1} step={0.01}
            value={value}
            onChange={(e) => onChange(Number(e.target.value))}
            className={styles.slider}
          />
        </div>
        <span className={styles.value}>
          {Math.round(value * 100)}%
        </span>
      </div>
    </div>
  );
}
