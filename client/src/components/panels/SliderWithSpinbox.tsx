import { useState } from "react";
import Form from "react-bootstrap/Form";
import LucideIcon from "../shared/LucideIcon";
import styles from "./SliderWithSpinbox.module.css";

interface SliderWithSpinboxProps {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  displayAsFloat?: boolean;
  /** Default value for the reset button. When not set, no reset button is shown. */
  defaultValue?: number;
  /** Fixed pixel width for the label column so sibling sliders align. */
  labelWidth?: number;
  /** When true, the label column is hidden entirely. */
  hideLabel?: boolean;
  onChange: (value: number) => void;
}

export default function SliderWithSpinbox({
  label,
  value,
  min,
  max,
  step,
  displayAsFloat = false,
  defaultValue,
  labelWidth,
  hideLabel = false,
  onChange,
}: SliderWithSpinboxProps) {
  const [hovered, setHovered] = useState(false);
  const [draftText, setDraftText] = useState<string | null>(null);
  const isChanged = defaultValue !== undefined && value !== defaultValue;

  const displayValue = displayAsFloat
    ? value.toFixed(2)
    : String(Math.round(value));

  const inputValue = draftText !== null ? draftText : displayValue;

  return (
    <div className={styles.row}>
        {/* Label — attached left */}
        {!hideLabel && (
          <span
            className={styles.label}
            style={labelWidth !== undefined ? { width: labelWidth, minWidth: labelWidth } : undefined}
          >
            {label}
          </span>
        )}

        {/* Range slider — attached middle */}
        <div className={styles.trackWrap}>
          <Form.Range
            min={min}
            max={max}
            step={step}
            value={value}
            onChange={(e) => onChange(Number(e.target.value))}
            className={styles.range}
          />
        </div>

        {/* Spinbox input + optional reset — attached right */}
        <div className={styles.spinWrap}>
          <Form.Control
            size="sm"
            type="text"
            inputMode="decimal"
            value={inputValue}
            onChange={(e) => {
              const raw = e.target.value.replace(/[^0-9.-]/g, "");
              setDraftText(raw);
              if (raw === "" || raw === "-" || raw.endsWith(".")) return;
              const v = Number(raw);
              if (isNaN(v)) return;
              onChange(Math.min(max, Math.max(min, v)));
            }}
            onBlur={() => {
              if (draftText !== null) {
                const v = Number(draftText.replace(/[^0-9.-]/g, ""));
                if (draftText !== "" && !isNaN(v)) {
                  onChange(Math.min(max, Math.max(min, v)));
                }
                setDraftText(null);
              }
            }}
            className={defaultValue !== undefined ? styles.spinInputWithReset : styles.spinInput}
          />
          {defaultValue !== undefined && (
            <button
              type="button"
              onMouseEnter={() => setHovered(true)}
              onMouseLeave={() => setHovered(false)}
              onClick={() => onChange(defaultValue)}
              disabled={!isChanged}
              title={`Reset to ${displayAsFloat ? defaultValue.toFixed(2) : defaultValue}`}
              className={isChanged ? styles.resetBtnActive : styles.resetBtn}
              style={hovered && isChanged ? { background: "rgba(0,132,185,0.15)" } : undefined}
            >
              <LucideIcon name="rotate-ccw-square" size={14} />
            </button>
          )}
      </div>
    </div>
  );
}
