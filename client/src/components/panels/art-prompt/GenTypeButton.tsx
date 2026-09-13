import type { RefObject } from "react";
import LucideIcon from "../../shared/LucideIcon";
import GenTypePopup from "./GenTypePopup";
import styles from "./GenTypeButton.module.css";

interface GenTypeButtonProps {
  genTypeBtnRef: RefObject<HTMLDivElement | null>;
  showGenType: boolean;
  toggleGenType: () => void;
  genTypeAnchor: { left: number; bottom: number } | null;
  generationType: "txt2img" | "img2img";
  onSetGenerationType: (v: "txt2img" | "img2img") => void;
  closeGenType: () => void;
}

export default function GenTypeButton({
  genTypeBtnRef,
  showGenType,
  toggleGenType,
  genTypeAnchor,
  generationType,
  onSetGenerationType,
  closeGenType,
}: GenTypeButtonProps) {
  return (
    <>
      <div ref={genTypeBtnRef}>
        <button
          type="button"
          title="Generation type"
          onClick={toggleGenType}
          className={showGenType ? styles.btnActive : styles.btn}
        >
          <LucideIcon name="image-plus" size={13} />
        </button>
      </div>
      <GenTypePopup
        anchor={showGenType ? genTypeAnchor : null}
        generationType={generationType}
        onSelect={(v) => {
          onSetGenerationType(v);
          closeGenType();
        }}
      />
    </>
  );
}
