import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import de from "./de.json";
import en from "./en.json";
import es from "./es.json";
import id from "./id.json";
import ja from "./ja.json";
import ko from "./ko.json";
import pt from "./pt.json";

export const FALLBACK_LANG = "en";
export const SUPPORTED_LANGS = ["de", "en", "es", "id", "ja", "ko", "pt"] as const;

// Initialize synchronously at module load time (inline resources require no
// async backend, so init completes before any React rendering).
i18n.use(initReactI18next).init({
  resources: {
    de: { translation: de },
    en: { translation: en },
    es: { translation: es },
    id: { translation: id },
    ja: { translation: ja },
    ko: { translation: ko },
    pt: { translation: pt },
  },
  lng: FALLBACK_LANG,
  fallbackLng: FALLBACK_LANG,
  interpolation: { escapeValue: false },
});

export default i18n;
