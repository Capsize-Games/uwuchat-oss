import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import Form from "react-bootstrap/Form";
import Spinner from "react-bootstrap/Spinner";
import {
  getSingleton,
  updateSingleton,
} from "@/api/client";
import { LANGUAGES } from "../../setup/LANGUAGES";
import { SUPPORTED_LANGS } from "../../../i18n";

const AVAILABLE_LANGUAGES = LANGUAGES.filter((l) =>
  SUPPORTED_LANGS.includes(l.code as typeof SUPPORTED_LANGS[number]),
);

export default function LanguageSection() {
  const { t, i18n } = useTranslation();
  const [detectedLanguage, setDetectedLanguage] = useState("en");
  const [userLanguage, setUserLanguage] = useState("en");
  const [botLanguage, setBotLanguage] = useState("en");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [appSettings, langSettings] = await Promise.all([
          getSingleton("ApplicationSettings"),
          getSingleton("LanguageSettings"),
        ]);
        if (cancelled) return;
        setDetectedLanguage(String(appSettings.detected_language ?? "en"));
        setUserLanguage(String(langSettings.user_language ?? "en"));
        setBotLanguage(String(langSettings.bot_language ?? "en"));
      } catch {
        // ignore
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  function handleDetectedLanguageChange(value: string) {
    setDetectedLanguage(value);
    updateSingleton("ApplicationSettings", {
      detected_language: value,
    } as Record<string, unknown>).catch(() => {});
    // Switch i18n language immediately so the UI re-renders.
    i18n.changeLanguage(value).catch(() => {});
  }

  function handleUserLanguageChange(value: string) {
    setUserLanguage(value);
    updateSingleton("LanguageSettings", {
      user_language: value,
      bot_language: botLanguage,
    } as Record<string, unknown>).catch(() => {});
  }

  function handleBotLanguageChange(value: string) {
    setBotLanguage(value);
    updateSingleton("LanguageSettings", {
      user_language: userLanguage,
      bot_language: value,
    } as Record<string, unknown>).catch(() => {});
  }

  if (loading) {
    return (
      <div className="text-center py-4">
        <Spinner animation="border" size="sm" />
      </div>
    );
  }

  return (
    <div>
      <h6 className="mb-3">{t("settings.language.heading")}</h6>

      <Form.Group className="mb-2">
        <Form.Label className="small">
          {t("settings.language.gui_label")}
        </Form.Label>
        <Form.Select
          size="sm"
          value={detectedLanguage}
          onChange={(e) => handleDetectedLanguageChange(e.target.value)}
          className="bg-dark text-light border-secondary"
        >
          {AVAILABLE_LANGUAGES.map((lang) => (
            <option key={lang.code} value={lang.code}>
              {lang.label}
            </option>
          ))}
        </Form.Select>
      </Form.Group>

      <Form.Group className="mb-2">
        <Form.Label className="small">
          {t("settings.language.user_label")}
        </Form.Label>
        <Form.Select
          size="sm"
          value={userLanguage}
          onChange={(e) => handleUserLanguageChange(e.target.value)}
          className="bg-dark text-light border-secondary"
        >
          {AVAILABLE_LANGUAGES.map((lang) => (
            <option key={lang.code} value={lang.code}>
              {lang.label}
            </option>
          ))}
        </Form.Select>
      </Form.Group>

      <Form.Group className="mb-3">
        <Form.Label className="small">
          {t("settings.language.uwu_label")}
        </Form.Label>
        <Form.Select
          size="sm"
          value={botLanguage}
          onChange={(e) => handleBotLanguageChange(e.target.value)}
          className="bg-dark text-light border-secondary"
        >
          {AVAILABLE_LANGUAGES.map((lang) => (
            <option key={lang.code} value={lang.code}>
              {lang.label}
            </option>
          ))}
        </Form.Select>
      </Form.Group>
    </div>
  );
}
