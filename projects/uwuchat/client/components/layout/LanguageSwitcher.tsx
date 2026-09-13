import { Globe } from "lucide-react";
import { LANGUAGES } from "../setup/LANGUAGES";
import { SUPPORTED_LANGS } from "../../i18n";
import { useUiLanguage } from "../../hooks/useUiLanguage";

const AVAILABLE_LANGUAGES = LANGUAGES.filter((l) =>
  SUPPORTED_LANGS.includes(l.code as (typeof SUPPORTED_LANGS)[number]),
);

export function LanguageSwitcher() {
  const { language, setLanguage } = useUiLanguage();

  return (
    <label className="public-nav-lang">
      <Globe size={16} strokeWidth={2} aria-hidden="true" />
      <select
        aria-label="Language"
        value={language}
        onChange={(e) => setLanguage(e.target.value)}
        className="public-nav-lang-select"
      >
        {AVAILABLE_LANGUAGES.map((lang) => (
          <option key={lang.code} value={lang.code}>
            {lang.native}
          </option>
        ))}
      </select>
    </label>
  );
}
