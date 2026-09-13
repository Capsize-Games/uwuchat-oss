import { useCallback, useEffect, useState } from "react";
import i18n, { FALLBACK_LANG, SUPPORTED_LANGS } from "../i18n";

type SupportedLang = (typeof SUPPORTED_LANGS)[number];

const LS_KEY = "airunner_ui_lang";

function isSupported(value: string): value is SupportedLang {
  return (SUPPORTED_LANGS as readonly string[]).includes(value);
}

function readStoredLang(): SupportedLang {
  try {
    const saved = localStorage.getItem(LS_KEY);
    if (saved && isSupported(saved)) return saved;
  } catch {
    /* localStorage unavailable */
  }
  return FALLBACK_LANG as SupportedLang;
}

/**
 * Drives the GUI language for logged-out visitors (landing, login,
 * register, etc). Signed-in users' saved ApplicationSettings language
 * (applied in AppBody) takes precedence once it loads.
 */
export function useUiLanguage() {
  const [language, setLanguageState] = useState<SupportedLang>(() =>
    readStoredLang(),
  );

  useEffect(() => {
    i18n.changeLanguage(language).catch(() => {});
  }, [language]);

  const setLanguage = useCallback((value: string) => {
    if (!isSupported(value)) return;
    setLanguageState(value);
    try {
      localStorage.setItem(LS_KEY, value);
    } catch {
      /* localStorage unavailable */
    }
  }, []);

  return { language, setLanguage };
}
