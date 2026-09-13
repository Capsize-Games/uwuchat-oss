import styles from "./ConnectingScreen.module.css";

export default function ConnectingScreen() {
  return (
    <div className={styles.wrap}>
      <div className={styles.radar}>
        {[0, 400, 800].map((delay) => (
          // eslint-disable-next-line no-restricted-syntax -- computed dimension from state/prop
          <div key={delay} className={styles.ring} style={{ animation: `uwu-pulse-ring 1.6s ${delay}ms ease-out infinite` }} />
        ))}
        <div className={styles.centerDot} />
      </div>
      <div className={styles.textBlock}>
        <div className={styles.title}>Connecting...</div>
        <div className={styles.subtitle}>We're connecting you to the UwUchat network&hellip;</div>
      </div>
    </div>
  );
}
