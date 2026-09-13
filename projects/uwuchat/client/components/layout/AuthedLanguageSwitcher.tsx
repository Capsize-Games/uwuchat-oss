import { useTranslation } from "react-i18next";
import styles from "./AuthedLanguageSwitcher.module.css";
import { useCallback, useEffect, useState } from "react";
import { Globe } from "lucide-react";
import i18n from "../../i18n";
import { LANGUAGES } from "../setup/LANGUAGES";
import { SUPPORTED_LANGS } from "../../i18n";
import { updateSingleton } from "@/api/client";
import { waitForBootstrap } from "@/features/api/WsApiClient";

const AVAILABLE_LANGUAGES = LANGUAGES.filter((l) => SUPPORTED_LANGS.includes(l.code as (typeof SUPPORTED_LANGS)[number]));

export default function AuthedLanguageSwitcher() {
  const [current, setCurrent] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    waitForBootstrap().then((payload) => {
      if (cancelled) return;
      try { const gui = ((payload.application_settings as Record<string, unknown>)?.detected_language ?? "en") as string; setCurrent(gui); } catch {}
    }).catch(() => {});
    return () => { cancelled = true; };
  }, []);
  const changeLang = useCallback(async (code: string) => {
    i18n.changeLanguage(code);
    setCurrent(code);
    updateSingleton("user_language", code).catch(() => {});
  }, []);
  if (!current) return null;
  return (
    <div className={styles.wrap}>
      <Globe size={14} color="var(--theme-text-secondary)" />
      <select value={current} onChange={(e) => changeLang(e.target.value)} className={styles.select}>
        {AVAILABLE_LANGUAGES.map((l) => <option key={l.code} value={l.code}>{l.native}</option>)}
      </select>
    </div>
  );
}
