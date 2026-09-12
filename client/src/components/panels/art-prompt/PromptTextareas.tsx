import { useRef, useEffect } from "react";
import { PromptDivider } from "./ArtShared";
import { useLocalStorage } from "../../../hooks/useLocalStorage";
import styles from "./PromptTextareas.module.css";

interface Props {
  prompt: string;
  secondaryPrompt: string;
  negativePrompt: string;
  secondaryNegativePrompt: string;
  isMultiPrompt: boolean;
  generating: boolean;
  onPromptChange: (v: string) => void;
  onSecondaryPromptChange: (v: string) => void;
  onNegativePromptChange: (v: string) => void;
  onSecondaryNegativePromptChange: (v: string) => void;
}

type FieldKey = "prompt" | "secondaryPrompt" | "negativePrompt" | "secondaryNegativePrompt";

export function PromptTextareas({
  prompt, secondaryPrompt, negativePrompt, secondaryNegativePrompt,
  isMultiPrompt, generating,
  onPromptChange, onSecondaryPromptChange, onNegativePromptChange, onSecondaryNegativePromptChange,
}: Props) {
  const [activeField, setActiveField] = useLocalStorage<FieldKey>(
    "airunner_active_prompt_field",
    "prompt" as FieldKey,
  );
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (activeField && textareaRef.current) {
      textareaRef.current.focus();
    }
  }, [activeField]);

  const fields: { key: FieldKey; label: string; placeholder: string; value: string; onChange: (v: string) => void }[] = [
    { key: "prompt", label: isMultiPrompt ? "Prompt 1" : "Prompt", placeholder: "Describe the image…", value: prompt, onChange: onPromptChange },
  ];
  if (isMultiPrompt) {
    fields.push(
      { key: "secondaryPrompt", label: "Prompt 2", placeholder: "Background, colors, atmosphere…", value: secondaryPrompt, onChange: onSecondaryPromptChange },
      { key: "negativePrompt", label: "Negative Prompt", placeholder: "Things to exclude…", value: negativePrompt, onChange: onNegativePromptChange },
      { key: "secondaryNegativePrompt", label: "Negative Prompt 2", placeholder: "Secondary negative…", value: secondaryNegativePrompt, onChange: onSecondaryNegativePromptChange },
    );
  }

  return (
    <div className="scroll-panel d-flex flex-column">
      {fields.map((f) => {
        const isSingle = !isMultiPrompt;
        const isActive = isSingle || activeField === f.key;
        return (
          // eslint-disable-next-line no-restricted-syntax -- state-driven conditional style
          <div key={f.key} className="d-flex flex-column" style={{ flex: isActive ? 1 : "0 0 auto" }}>
            <PromptDivider label={f.label} />
            <div
              className={`prompt-textarea-bg${isActive ? ` ${styles.activeWrap}` : ""}`}
              // eslint-disable-next-line no-restricted-syntax -- state-driven conditional style
              style={{ flex: isActive ? 1 : "0 0 auto" }}
              onClick={() => {
                if (isActive && textareaRef.current) {
                  textareaRef.current.focus();
                }
              }}
            >
              {isActive ? (
                <textarea
                  ref={textareaRef}
                  className={styles.textarea}
                  value={f.value}
                  onChange={(e) => f.onChange(e.target.value)}
                  placeholder={f.placeholder}
                  disabled={generating}
                />
              ) : (
                <div
                  className={styles.collapsed}
                  onClick={() => setActiveField(f.key)}
                  title="Click to expand"
                >
                  {f.value || f.placeholder}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
