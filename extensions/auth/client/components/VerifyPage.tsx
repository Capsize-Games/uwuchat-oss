/**
 * Email verification page — shown at /verify?token=xxx.
 *
 * Reads the verification token from the URL and calls
 * ``GET /api/v1/auth/verify?token=xxx`` on mount.
 * Displays a success or error message and links to login.
 */

import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

type VerifyState = "loading" | "success" | "already-verified" | "error";

export default function VerifyPage() {
  const navigate = useNavigate();
  const [state, setState] = useState<VerifyState>("loading");
  const [message, setMessage] = useState("");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const token = params.get("token");

    if (!token) {
      setState("error");
      setMessage("Missing verification token.");
      return;
    }

    fetch(`/api/v1/auth/verify?token=${encodeURIComponent(token)}`)
      .then(async (res) => {
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || "Verification failed");
        }
        return res.json();
      })
      .then((data) => {
        if (data.already_verified) {
          setState("already-verified");
          setMessage("Your email is already verified.");
        } else {
          setState("success");
          setMessage("Email verified successfully!");
        }
      })
      .catch((err) => {
        setState("error");
        setMessage(err instanceof Error ? err.message : "Verification failed");
      });
  }, []);

  return (
    <div style={{ maxWidth: 400, margin: "80px auto", padding: 24, textAlign: "center" }}>
      <h1>Email Verification</h1>

      {state === "loading" && (
        <p style={{ color: "#6b7280", marginTop: 24 }}>Verifying your email…</p>
      )}

      {state === "success" && (
        <>
          <p style={{ color: "#059669", marginTop: 24, fontSize: 18 }}>
            ✅ {message}
          </p>
          <button
            onClick={() => navigate("/login?verified=1")}
            style={{ marginTop: 24, padding: "8px 24px" }}
          >
            Sign In
          </button>
        </>
      )}

      {state === "already-verified" && (
        <>
          <p style={{ color: "#6b7280", marginTop: 24, fontSize: 18 }}>
            ℹ️ {message}
          </p>
          <button
            onClick={() => navigate("/login")}
            style={{ marginTop: 24, padding: "8px 24px" }}
          >
            Sign In
          </button>
        </>
      )}

      {state === "error" && (
        <>
          <p style={{ color: "red", marginTop: 24, fontSize: 18 }}>
            ❌ {message}
          </p>
          <button
            onClick={() => navigate("/login")}
            style={{ marginTop: 24, padding: "8px 24px" }}
          >
            Back to Sign In
          </button>
        </>
      )}
    </div>
  );
}
