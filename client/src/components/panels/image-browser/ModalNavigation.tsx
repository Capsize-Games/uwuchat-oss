import styles from "./ModalNavigation.module.css";

interface Props {
  currentIndex: number;
  total: number;
  onPrev: () => void;
  onNext: () => void;
}

export default function ModalNavigation({ currentIndex, total, onPrev, onNext }: Props) {
  const atStart = currentIndex <= 0;
  const atEnd = currentIndex >= total - 1;

  return (
    <div className={styles.row}>
      <button
        onClick={onPrev}
        disabled={atStart}
        className={atStart ? styles.btnDisabled : styles.btn}
      >
        ◀ Previous
      </button>
      <span className={styles.index}>
        {currentIndex + 1} / {total}
      </span>
      <button
        onClick={onNext}
        disabled={atEnd}
        className={atEnd ? styles.btnDisabled : styles.btn}
      >
        Next ▶
      </button>
    </div>
  );
}
