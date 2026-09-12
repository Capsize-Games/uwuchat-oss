import Form from "react-bootstrap/Form";
import styles from "./ConversationSection.module.css";

interface Props {
  performConversationSummary: boolean;
  summarizeAfterNTurns: number;
  onSummaryToggle: (v: boolean) => void;
  onTurnsChange: (v: number) => void;
}

export default function ConversationSection({
  performConversationSummary, summarizeAfterNTurns, onSummaryToggle, onTurnsChange,
}: Props) {
  return (
    <div className={`p-2 mt-2 ${styles.section}`}>
      <span className={`text-theme-secondary d-block ${styles.title}`}>
        Conversation Summarization
      </span>
      <Form.Check
        type="switch"
        id="llm-perform-summary"
        label={<span className="text-theme-secondary">Auto-summarize long conversations</span>}
        checked={performConversationSummary}
        onChange={(e) => onSummaryToggle(e.target.checked)}
      />
      {performConversationSummary && (
        <Form.Group className="mt-2">
          <Form.Label className={`text-theme-secondary ${styles.label}`}>
            Summarize after <strong>{summarizeAfterNTurns}</strong> conversation turns
          </Form.Label>
          <Form.Range
            min={2} max={50} step={1}
            value={summarizeAfterNTurns}
            onChange={(e) => onTurnsChange(Number(e.target.value))}
            className={styles.range}
          />
        </Form.Group>
      )}
    </div>
  );
}
