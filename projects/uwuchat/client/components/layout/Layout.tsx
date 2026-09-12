import { type ReactNode } from "react";
import TopBar from "./TopBar";
import styles from "./Layout.module.css";

interface LayoutProps { children: ReactNode; }

export default function Layout({ children }: LayoutProps) {
  return (
    <div className={`app-shell ${styles.root}`}>
      <TopBar />
      <div className="main-row">
        <div className="flex-grow-1 d-flex overflow-hidden min-w-0">
          <div className={`chat-panel ${styles.content}`}>
            {children}
          </div>
        </div>
      </div>
    </div>
  );
}
