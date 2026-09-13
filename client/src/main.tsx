import "./styles/custom.scss";

import * as Sentry from "@sentry/react";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { DeploymentProvider } from "./context/DeploymentContext";
import App from "./App";
import styles from "./main.module.css";

if (import.meta.env.VITE_SENTRY_DSN) {
  Sentry.init({
    dsn: import.meta.env.VITE_SENTRY_DSN,
    environment: import.meta.env.MODE,
    tracesSampleRate: 0.1,
    beforeSend(event) {
      if (event.request?.data) {
        delete event.request.data;
      }
      return event;
    },
  });
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Sentry.ErrorBoundary
      fallback={
        <div className={styles.errorBoundary}>
          <h2>Something went wrong</h2>
          <p>
            An unexpected error occurred. Please refresh the page to try again.
          </p>
        </div>
      }
    >
      <BrowserRouter>
        <DeploymentProvider>
          <App />
        </DeploymentProvider>
      </BrowserRouter>
    </Sentry.ErrorBoundary>
  </StrictMode>,
);
