/**
 * UwUchat — GDPR / Colorado CPA data request page (/data-request).
 *
 * Two paths:
 *  - Logged in: one-click self-service account deletion via the API.
 *  - Not logged in: mailto link to submit a deletion request manually.
 */

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth";
import { PublicShell } from "../layout/PublicShell";

export default function DataRequest() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { user, isAuthenticated, deleteAccount, accessToken } = useAuth();
  const [confirming, setConfirming] = useState(false);
  const [password, setPassword] = useState("");
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleted, setDeleted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isExporting, setIsExporting] = useState(false);

  const handleExportRequest = async () => {
    setError(null);
    setIsExporting(true);
    try {
      if (!accessToken) {
        throw new Error("Not authenticated");
      }
      const res = await fetch("/api/v1/auth/data-export", {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(
          err.detail || t("legal.data_request.export_error"),
        );
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "uwuchat-data-export.json";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : t("legal.data_request.export_error"),
      );
    } finally {
      setIsExporting(false);
    }
  };

  const handleDeleteRequest = async () => {
    setError(null);
    setIsDeleting(true);
    try {
      await deleteAccount(password);
      setDeleted(true);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : t("legal.data_request.deleting"),
      );
      setIsDeleting(false);
      setConfirming(false);
    }
  };

  if (deleted) {
    return (
      <PublicShell>
        <div className="legal-page">
          <div className="legal-container">
            <div className="legal-content">
              <h1>{t("legal.data_request.account_deleted_title")}</h1>
              <p>
                {t("legal.data_request.deleted_desc")}{" "}
                <a href="/privacy" className="auth-link">Privacy Policy</a>.
              </p>
              <p>
                {t("legal.data_request.deleted_email_desc")}{" "}
                <a href="mailto:privacy@uwuchat.com" className="auth-link">
                  privacy@uwuchat.com
                </a>
                .
              </p>
              <button
                className="btn btn-primary"
                onClick={() => navigate("/login")}
              >
                {t("legal.data_request.return_login")}
              </button>
            </div>
          </div>
        </div>
      </PublicShell>
    );
  }

  return (
    <PublicShell>
      <div className="legal-page">
        <div className="legal-container">
          <div className="legal-content">
            <h1>{t("legal.data_request.title")}</h1>

            <p>
              Under the GDPR (Article 17) and the Colorado Privacy Act, you have
              the right to request deletion of your personal data ("right to
              erasure").
            </p>

            {isAuthenticated && user ? (
              <>
                <p>
                  You are currently signed in as{" "}
                  <strong>{user.email}</strong>.
                </p>

                <p>
                  {t("legal.data_request.export_desc")}
                </p>

                <button
                  className="btn btn-outline"
                  onClick={handleExportRequest}
                  disabled={isExporting}
                >
                  {isExporting
                    ? t("legal.data_request.exporting")
                    : t("legal.data_request.export_my_data")}
                </button>

                <hr />

                <p>
                  {t("legal.data_request.delete_desc_paragraph")}
                </p>

                <div
                  className="legal-warning-box"
                >
                  <p>
                    <strong>What happens when you delete your account:</strong>
                  </p>
                  <ul>
                    <li>Your account is deactivated immediately</li>
                    <li>All personal data (email, characters, chat history) is permanently purged within 30 days</li>
                    <li>Payment records are retained for 7 years as required by law</li>
                    <li>This action cannot be undone</li>
                  </ul>
                </div>

                {error && (
                  <div className="alert alert-danger py-2 mb-3" role="alert">
                    {error}
                  </div>
                )}

                {!confirming ? (
                  <button
                    className="btn btn-danger"
                    onClick={() => setConfirming(true)}
                  >
                    {t("legal.data_request.delete_my_account")}
                  </button>
                ) : (
                    <div>
                      <p>
                        {t("legal.data_request.confirm_delete")}
                      </p>
                      <div className="mb-3">
                        <label
                          htmlFor="delete-password"
                          className="form-label"
                        >
                          Enter your password to confirm:
                        </label>
                        <input
                          id="delete-password"
                          type="password"
                          className="form-control"
                          value={password}
                          onChange={(e) => setPassword(e.target.value)}
                          autoComplete="current-password"
                          placeholder="Your password"
                        />
                      </div>
                      <div className="d-flex gap-2">
                      <button
                        className="btn btn-secondary"
                        onClick={() => setConfirming(false)}
                        disabled={isDeleting}
                      >
                        {t("legal.data_request.cancel")}
                      </button>
                      <button
                        className="btn btn-danger"
                        onClick={handleDeleteRequest}
                        disabled={isDeleting}
                      >
                        {isDeleting
                          ? t("legal.data_request.deleting")
                          : t("legal.data_request.yes_delete")}
                      </button>
                    </div>
                  </div>
                )}

                <hr />

                <p>
                  {t("legal.data_request.other_requests")}{" "}
                  <a href="mailto:privacy@uwuchat.com" className="auth-link">
                    privacy@uwuchat.com
                  </a>
                  . {t("legal.data_request.respond_time")}
                </p>
              </>
            ) : (
              <>
                <p>
                  To request deletion of your account and personal data, please
                  sign in to your account — we can then delete it immediately from
                  your settings.
                </p>

                <button
                  className="btn btn-primary"
                  onClick={() => navigate("/login")}
                >
                  {t("legal.data_request.sign_in_to_delete")}
                </button>

                <hr />

                <p>
                  {t("legal.data_request.no_access_desc")}
                </p>

                <a
                  href="mailto:privacy@uwuchat.com?subject=Account%20Deletion%20Request&body=Please%20delete%20my%20UwU%20Chat%20account%20and%20all%20associated%20data.%0A%0AEmail%20address%3A%20%5Byour%20email%5D%0A%0AAdditional%20details%3A%20"
                  className="btn btn-outline"
                >
                  {t("legal.data_request.email_privacy")}
                </a>

                <p>
                  {t("legal.data_request.respond_30_days")}
                </p>
              </>
            )}
          </div>
        </div>
      </div>
    </PublicShell>
  );
}
