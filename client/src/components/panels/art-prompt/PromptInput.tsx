import Form from "react-bootstrap/Form";
import styles from "./PromptInput.module.css";

export default function PromptInput({
  label,
  value,
  onChange,
  placeholder,
  disabled,
}: {
  label: string;
  value: string;
  onChange: (val: string) => void;
  placeholder?: string;
  disabled?: boolean;
}) {
  return (
    <Form.Group
      className="flex-grow-1 d-flex flex-column min-h-0"
    >
      {label ? (
        <div className={styles.label}>
          {label}
        </div>
      ) : null}
      <Form.Control
        as="textarea"
        className="flex-grow-1 min-h-0"
        // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
        style={{
          resize: "none",
          width: "100%",
          ...(label
            ? { borderTopLeftRadius: 0, borderTopRightRadius: 0 }
            : {}),
        }}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
      />
    </Form.Group>
  );
}
