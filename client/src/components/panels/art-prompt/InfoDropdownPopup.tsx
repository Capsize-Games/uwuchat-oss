import { createPortal } from "react-dom";
import type { ArtOptionsResponse } from "../../../api/client";
import styles from "./InfoDropdownPopup.module.css";

interface InfoDropdownPopupProps {
  field: string | null;
  anchor: { left: number; bottom: number; minWidth: number } | null;
  version: string;
  modelPath: string;
  scheduler: string;
  generationType: "txt2img" | "img2img" | "inpaint";
  artOptions: ArtOptionsResponse | null;
  availableSchedulers: { label: string; value: string }[];
  onSelectVersion: (v: string) => void;
  onSelectModel: (m: string) => void;
  onSelectScheduler: (s: string) => void;
  onSelectGenType: (v: "txt2img" | "img2img" | "inpaint") => void;
  onClose: () => void;
}

function genTypeBtn(
  type: "txt2img" | "img2img" | "inpaint",
  current: "txt2img" | "img2img" | "inpaint",
  onSelect: (v: "txt2img" | "img2img" | "inpaint") => void,
  onClose: () => void,
) {
  const active = type === current;
  const label = type === "txt2img" ? "Text-to-image" : type === "img2img" ? "Image-to-image" : "Inpaint";
  const desc = type === "txt2img"
    ? "Generate from a text description alone"
    : type === "img2img"
      ? "Transform an existing image with a text prompt"
      : "Edit specific areas of an image using a mask";
  return (
    <button type="button"
      onClick={() => { onSelect(type); onClose(); }}
      className={active ? styles.genTypeBtnActive : styles.genTypeBtn}
    >
      <span>{label}</span>
      <span className={styles.genTypeDesc}>{desc}</span>
    </button>
  );
}

export default function InfoDropdownPopup({
  field, anchor, version, modelPath, scheduler, generationType,
  artOptions, availableSchedulers,
  onSelectVersion, onSelectModel, onSelectScheduler,
  onSelectGenType, onClose,
}: InfoDropdownPopupProps) {
  if (!field || !anchor) return null;

  return createPortal(
    <div id="art-info-dropdown-popup" className={`bg-theme-panel overflow-y-auto ${styles.popup}`}
      // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
      style={{
        left: anchor.left, bottom: anchor.bottom,
        minWidth: Math.max(anchor.minWidth, 160), maxWidth: 280,
      }}
    >
      {field === "gentype" ? (
        <>
          {genTypeBtn("txt2img", generationType, onSelectGenType, onClose)}
          {genTypeBtn("img2img", generationType, onSelectGenType, onClose)}
          {version !== "Z-Image Turbo" && genTypeBtn("inpaint", generationType, onSelectGenType, onClose)}
        </>
      ) : (
        (() => {
          const options =
            field === "version"
              ? (artOptions?.versions?.map((v) => ({ label: v.name, value: v.name })) ?? [])
              : field === "model"
                ? (artOptions?.versions?.find((v) => v.name === version)?.models ?? [])
                : availableSchedulers;

          if (options.length === 0) {
            return <div className={styles.noOptions}>No options</div>;
          }

          return options.map((opt: { label: string; value: string }) => {
            const currentValue = field === "version" ? version : field === "model" ? modelPath : scheduler;
            return (
              <button key={opt.value} type="button"
                onClick={() => {
                  if (field === "version") onSelectVersion(opt.value);
                  else if (field === "model") onSelectModel(opt.value);
                  else onSelectScheduler(opt.value);
                  onClose();
                }}
                className={opt.value === currentValue ? styles.optActive : styles.opt}
              >
                {opt.label}
              </button>
            );
          });
        })()
      )}
    </div>,
    document.body,
  );
}
