/**
 * Shared card shell for all auth pages (login, register, verify, etc.).
 *
 * Uses Bootstrap 5 + AIRunner theme CSS variables so it matches the
 * rest of the app regardless of which theme is active.
 */

import { ReactNode } from "react";
import "./auth.scss";

interface AuthCardProps {
  title: string;
  children: ReactNode;
}

export function AuthCard({ title, children }: AuthCardProps) {
  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1 className="auth-title">{title}</h1>
        {children}
      </div>
    </div>
  );
}
