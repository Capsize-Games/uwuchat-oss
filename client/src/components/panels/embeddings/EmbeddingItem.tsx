import Form from "react-bootstrap/Form";
import styles from "./EmbeddingItem.module.css";

interface EmbeddingRecord {
  id: number;
  name: string;
  path: string;
  enabled: boolean;
  trigger_words: string[];
  _inputText: string;
}

export default function EmbeddingItem({
  item,
  onToggle,
  onCopyWord,
  onDeleteWord,
  onAddWords,
  onInputChange,
  onInputKeyDown,
}: {
  item: EmbeddingRecord;
  onToggle: (id: number, enabled: boolean) => void;
  onCopyWord: (word: string) => void;
  onDeleteWord: (id: number, word: string) => void;
  onAddWords: (id: number) => void;
  onInputChange: (id: number, value: string) => void;
  onInputKeyDown: (e: React.KeyboardEvent, id: number) => void;
}) {
  return (
    <div key={item.id} className={`mb-3 p-2 rounded ${styles.card}`}>
      <div className="d-flex align-items-center gap-2 mb-1">
        <Form.Check
          type="switch"
          checked={item.enabled}
          onChange={(e) => onToggle(item.id, e.target.checked)}
          id={`embed-enable-${item.id}`}
        />
        <span className={`small ${item.enabled ? styles.nameEnabled : styles.nameDisabled}`}>
          {item.name}
        </span>
      </div>

      {Array.isArray(item.trigger_words) && item.trigger_words.length > 0 && (
        <div className="d-flex flex-wrap gap-1 mb-1">
          {item.trigger_words.map((word) => (
            <span
              key={word}
              onClick={() => onCopyWord(word)}
              title="Click to copy"
              className={styles.word}
            >
              <span
                className={styles.wordClose}
                onClick={(e) => {
                  e.stopPropagation();
                  onDeleteWord(item.id, word);
                }}
                title="Remove trigger word"
              >
                ✕
              </span>
              {word}
            </span>
          ))}
        </div>
      )}

      <div className="d-flex gap-1">
        <Form.Control
          size="sm"
          type="text"
          placeholder="Add trigger words (comma-separated)..."
          value={item._inputText}
          onChange={(e) => onInputChange(item.id, e.target.value)}
          onKeyDown={(e) => onInputKeyDown(e, item.id)}
          className={styles.input}
        />
        <button
          className={`btn btn-sm ${styles.addBtn}`}
          onClick={() => onAddWords(item.id)}
          disabled={!item._inputText.trim()}
        >
          Add
        </button>
      </div>
    </div>
  );
}
